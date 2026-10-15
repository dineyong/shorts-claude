"""발행 큐. 초안 → 발행 대기 → (업로드, 공개 예약) → 공개됨.
유튜브에는 private + publishAt 으로 미리 올려 두므로, 이 프로그램이 꺼져 있어도 시각에 공개된다."""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo
from . import body as bodymod, checks, db
from .errors import NotAuthorized, PublishError
from .schedule import next_free_slot, norm

MAX_ATTEMPTS = 5


class ValidationError(Exception):
    def __init__(self, errors: list):
        super().__init__("; ".join(errors))
        self.errors = errors


def _taken(channel_id: str, tz: str, exclude_id: int | None = None) -> set:
    return {norm(v["publish_at"], tz) for v in db.list_videos()
            if v["channel_id"] == channel_id and v["publish_at"] and v["id"] != exclude_id
            and v["status"] in ("queued", "uploaded", "published")}


def _channel_for(v: dict, s: dict) -> str:
    return s["channel_map"].get(v.get("category") or "longform", "default")


def _slots_for(v: dict, s: dict) -> list:
    return s["longform"]["slots"] if v["format"] == "longform" else s["shorts"]["slots"]


def enqueue(vid: int, publish_at: str | None = None, now: dt.datetime | None = None) -> dict:
    s = db.get_settings()
    v = db.get_video(vid)
    if not v:
        raise KeyError(vid)
    if v["status"] in ("uploaded", "published"):
        raise ValueError("이미 업로드된 영상입니다")
    errors, warns = checks.validate_video(v, s)
    if errors:
        raise ValidationError(errors)
    tz = s["timezone"]
    now = (now or dt.datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
    ch = _channel_for(v, s)
    if publish_at:
        at = norm(publish_at, tz)
        if dt.datetime.fromisoformat(at) < now + dt.timedelta(minutes=s["min_lead_min"]):
            raise ValidationError([f"공개 시각은 지금부터 {s['min_lead_min']}분 이후여야 합니다"])
    else:
        at = next_free_slot(_slots_for(v, s), tz, _taken(ch, tz, vid), now, s["min_lead_min"])
    db.update_video(vid, status="queued", publish_at=at, channel_id=ch, attempts=0,
                    next_attempt_at=None, error=None)
    return {"publish_at": at, "warnings": warns}


def unqueue(vid: int) -> None:
    v = db.get_video(vid)
    if v and v["status"] in ("queued", "failed"):
        db.update_video(vid, status="draft", publish_at=None, error=None, attempts=0, next_attempt_at=None)
    else:
        raise ValueError("발행 대기/실패 상태에서만 취소할 수 있습니다")


def _today_count(tz: str, now: dt.datetime) -> int:
    n = 0
    for v in db.list_videos():
        if v["uploaded_at"] and v["status"] in ("uploaded", "published"):
            if dt.datetime.fromisoformat(v["uploaded_at"]).astimezone(ZoneInfo(tz)).date() == now.date():
                n += 1
    return n


def process_queue(client_for, now: dt.datetime | None = None) -> dict:
    """발행 대기 영상을 유튜브에 올린다. client_for(channel_id, settings) -> 클라이언트."""
    s = db.get_settings()
    tz = s["timezone"]
    now = (now or dt.datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
    result = {"uploaded": [], "failed": [], "deferred": []}
    queued = sorted(db.list_videos(status="queued"), key=lambda v: v["publish_at"] or "")
    done_today = _today_count(tz, now)
    for v in queued:
        if v["next_attempt_at"] and dt.datetime.fromisoformat(v["next_attempt_at"]) > now:
            result["deferred"].append(v["id"])
            continue
        if done_today >= s["daily_upload_cap"]:
            result["deferred"].append(v["id"])
            continue
        errors, _ = checks.validate_video(v, s)            # 큐에 있는 동안 파일이 사라졌을 수도
        if errors:
            db.update_video(v["id"], status="failed", error="; ".join(errors))
            result["failed"].append(v["id"])
            continue
        # 공개 예약 시각이 이미 지났거나 임박했으면 다음 슬롯으로 옮긴다
        if dt.datetime.fromisoformat(v["publish_at"]) < now + dt.timedelta(minutes=5):
            at = next_free_slot(_slots_for(v, s), tz, _taken(v["channel_id"], tz, v["id"]), now, s["min_lead_min"])
            db.log("info", f"#{v['id']} 예약 시각이 지나 {at} 로 옮겼습니다")
            db.update_video(v["id"], publish_at=at)
            v["publish_at"] = at
        client = client_for(v["channel_id"], s)
        body, part = bodymod.build(v, s)
        try:
            yt_id = client.upload(v["file_path"], body, part)
        except PublishError as e:
            attempts = v["attempts"] + (1 if e.count_attempt else 0)
            if e.fatal or attempts >= MAX_ATTEMPTS:
                db.update_video(v["id"], status="failed", error=str(e), attempts=attempts)
                result["failed"].append(v["id"])
                db.log("error", f"#{v['id']} 업로드 실패: {e}")
            else:
                wait = e.retry_minutes or min(5 * 2 ** attempts, 360)
                nxt = (now + dt.timedelta(minutes=wait)).isoformat(timespec="seconds")
                db.update_video(v["id"], error=str(e), attempts=attempts, next_attempt_at=nxt)
                result["deferred"].append(v["id"])
                db.log("warn", f"#{v['id']} 업로드 보류({wait}분 후 재시도): {e}")
            continue
        db.update_video(v["id"], status="uploaded", youtube_id=yt_id, uploaded_at=now.isoformat(timespec="seconds"),
                        error=None, next_attempt_at=None)
        db.log("info", f"#{v['id']} 업로드 완료 → {yt_id} (공개 예약 {v['publish_at']})")
        result["uploaded"].append(v["id"])
        done_today += 1
    return result


def sync_published(client_for, now: dt.datetime | None = None) -> dict:
    """공개 시각이 지난 영상이 실제로 공개됐는지 확인한다."""
    s = db.get_settings()
    tz = s["timezone"]
    now = (now or dt.datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
    out = {"published": [], "missing": [], "waiting": []}
    due = [v for v in db.list_videos(status="uploaded")
           if v["youtube_id"] and dt.datetime.fromisoformat(v["publish_at"]) <= now]
    by_channel = {}
    for v in due:
        by_channel.setdefault(v["channel_id"], []).append(v)
    for ch, vs in by_channel.items():
        try:
            info = client_for(ch, s).stats([v["youtube_id"] for v in vs] if True else [])
        except PublishError as e:
            db.log("warn", f"공개 확인 보류: {e}")
            continue
        for v in vs:
            r = info.get(v["youtube_id"], {"exists": False})
            if not r.get("exists"):
                db.update_video(v["id"], status="failed", error="유튜브에서 영상을 찾을 수 없습니다(삭제됨?)")
                out["missing"].append(v["id"])
            elif r.get("privacy") == "public":
                db.update_video(v["id"], status="published", error=None)
                out["published"].append(v["id"])
            else:
                late = now - dt.datetime.fromisoformat(v["publish_at"]) > dt.timedelta(minutes=30)
                if late:
                    db.update_video(v["id"], error="공개 시각이 지났지만 아직 비공개입니다. 스튜디오에서 확인하세요")
                out["waiting"].append(v["id"])
    return out
