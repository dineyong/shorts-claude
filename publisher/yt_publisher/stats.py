"""통계 수집(스냅샷)과 집계. 유튜브 Data API videos.list 는 호출당 1유닛, 50개씩 묶어 조회한다."""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo
from . import db
from .catalog import SHORTS_CATEGORIES
from .errors import PublishError


def _p(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso)


def interval_for(age_hours: float, base_min: int) -> int:
    """영상이 오래될수록 수집 간격을 늘린다(분)."""
    if age_hours < 48:
        return base_min
    if age_hours < 14 * 24:
        return max(base_min, 360)
    return max(base_min, 1440)


def collect(client_for, now: dt.datetime | None = None, force: bool = False) -> dict:
    s = db.get_settings()
    tz = ZoneInfo(s["timezone"])
    now = (now or dt.datetime.now(tz)).astimezone(tz)
    out = {"sampled": [], "missing": [], "skipped": 0}
    due = []
    for v in db.list_videos(status="published"):
        if not v["youtube_id"]:
            continue
        snaps = db.snapshots(v["id"])
        if snaps and not force:
            age_h = (now - _p(v["publish_at"])).total_seconds() / 3600
            gap = (now - _p(snaps[-1]["captured_at"])).total_seconds() / 60
            if gap < interval_for(age_h, s["stats_interval_min"]):
                out["skipped"] += 1
                continue
        due.append(v)
    by_channel = {}
    for v in due:
        by_channel.setdefault(v["channel_id"], []).append(v)
    for ch, vs in by_channel.items():
        try:
            info = client_for(ch, s).stats([v["youtube_id"] for v in vs])
        except PublishError as e:
            db.log("warn", f"통계 수집 보류: {e}")
            continue
        for v in vs:
            r = info.get(v["youtube_id"], {"exists": False})
            if not r.get("exists"):
                db.update_video(v["id"], error="유튜브에서 영상을 찾을 수 없습니다(삭제됨?)")
                out["missing"].append(v["id"])
                continue
            db.add_snapshot(v["id"], r["views"], r["likes"], r["comments"], now.isoformat(timespec="seconds"))
            out["sampled"].append(v["id"])
    return out


def _at_or_before(snaps: list, t: dt.datetime):
    best = None
    for sn in snaps:
        if _p(sn["captured_at"]) <= t:
            best = sn
        else:
            break
    return best


def video_summary(v: dict, now: dt.datetime) -> dict:
    snaps = db.snapshots(v["id"])
    res = {"id": v["id"], "title": v["title"], "format": v["format"], "category": v["category"],
           "youtube_id": v["youtube_id"], "publish_at": v["publish_at"], "status": v["status"],
           "views": 0, "likes": 0, "comments": 0, "views_24h": None, "views_7d": None,
           "like_rate": None, "last_collected_at": None, "snapshots": len(snaps)}
    if not snaps:
        return res
    last = snaps[-1]
    res.update(views=last["views"], likes=last["likes"], comments=last["comments"], last_collected_at=last["captured_at"])
    if last["views"]:
        res["like_rate"] = round(last["likes"] / last["views"] * 100, 2)
    for key, hours in (("views_24h", 24), ("views_7d", 24 * 7)):
        base = _at_or_before(snaps, _p(last["captured_at"]) - dt.timedelta(hours=hours))
        if base is None:
            # 아직 그만큼 쌓이지 않음: 공개 후 48시간 안에 찍힌 첫 스냅샷이면 공개 이후 전체를 증가분으로 본다
            first = snaps[0]
            fresh = (_p(first["captured_at"]) - _p(v["publish_at"])).total_seconds() < 48 * 3600
            res[key] = last["views"] - (0 if fresh else first["views"])
        else:
            res[key] = last["views"] - base["views"]
    return res


def overview(now: dt.datetime | None = None, fmt: str | None = None) -> dict:
    s = db.get_settings()
    tz = ZoneInfo(s["timezone"])
    now = (now or dt.datetime.now(tz)).astimezone(tz)
    vids = db.list_videos(fmt=fmt)
    counts = {}
    for v in vids:
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    rows = [video_summary(v, now) for v in vids if v["status"] == "published"]
    groups = {}
    for r in rows:
        key = r["category"] or "longform"
        g = groups.setdefault(key, {"videos": 0, "views": 0, "likes": 0, "comments": 0, "views_24h": 0})
        g["videos"] += 1
        for k in ("views", "likes", "comments"):
            g[k] += r[k]
        g["views_24h"] += r["views_24h"] or 0
    for g in groups.values():
        g["avg_views"] = round(g["views"] / g["videos"]) if g["videos"] else 0
    total = {k: sum(g[k] for g in groups.values()) for k in ("videos", "views", "likes", "comments", "views_24h")}
    top = sorted(rows, key=lambda r: (r["views_24h"] or 0, r["views"]), reverse=True)[:5]
    last = max((r["last_collected_at"] for r in rows if r["last_collected_at"]), default=None)
    return {"counts": counts, "total": total, "by_category": groups, "top": top,
            "last_collected_at": last, "videos": rows}


def daily_series(days: int = 14, now: dt.datetime | None = None, category: str | None = None,
                 fmt: str | None = None) -> list:
    """날짜별 조회수 증가분 합계. 카테고리/포맷으로 거를 수 있다."""
    s = db.get_settings()
    tz = ZoneInfo(s["timezone"])
    now = (now or dt.datetime.now(tz)).astimezone(tz)
    today = now.date()
    dates = [today - dt.timedelta(days=i) for i in range(days - 1, -1, -1)]
    totals = {d: {"views": 0, "likes": 0} for d in dates}
    for v in db.list_videos(fmt=fmt, category=category, status="published"):
        snaps = db.snapshots(v["id"])
        if not snaps:
            continue
        fresh = (_p(snaps[0]["captured_at"]) - _p(v["publish_at"])).total_seconds() < 48 * 3600
        prev_v, prev_l = (0, 0) if fresh else (snaps[0]["views"], snaps[0]["likes"])
        for d in sorted({_p(sn["captured_at"]).astimezone(tz).date() for sn in snaps}):
            last_of_day = [sn for sn in snaps if _p(sn["captured_at"]).astimezone(tz).date() <= d][-1]
            if d in totals:
                totals[d]["views"] += last_of_day["views"] - prev_v
                totals[d]["likes"] += last_of_day["likes"] - prev_l
            prev_v, prev_l = last_of_day["views"], last_of_day["likes"]
    return [{"date": d.isoformat(), **totals[d]} for d in dates]
