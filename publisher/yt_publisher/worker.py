"""백그라운드 작업자. 주기적으로: 폴더 읽기 → 자동 대기열 → 업로드 → 공개 확인 → 통계 수집."""
from __future__ import annotations
import datetime as dt
import threading
import traceback
from zoneinfo import ZoneInfo
from . import db, inbox, publisher, stats
from .youtube import client_for as default_client_for

_lock = threading.Lock()
TICK_SECONDS = 30


def run_once(client_for=default_client_for, now: dt.datetime | None = None, force_stats: bool = False) -> dict:
    """한 번 돌린다. 동시에 두 번 실행되지 않도록 잠근다."""
    if not _lock.acquire(blocking=False):
        return {"busy": True}
    try:
        s = db.get_settings()
        tz = ZoneInfo(s["timezone"])
        now = (now or dt.datetime.now(tz)).astimezone(tz)
        res = {}
        res["inbox"] = inbox.scan_inbox()
        res["auto_queued"] = _auto_queue(s, now)
        res["publish"] = publisher.process_queue(client_for, now)
        res["sync"] = publisher.sync_published(client_for, now)
        res["stats"] = stats.collect(client_for, now, force=force_stats)
        with_ts = now.isoformat(timespec="seconds")
        with db.connect() as c:
            c.execute("INSERT INTO kv(key,value) VALUES('last_tick',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (with_ts,))
        return res
    finally:
        _lock.release()


def _auto_queue(s: dict, now: dt.datetime) -> list:
    wanted = set(s.get("auto_queue") or [])
    queued = []
    if not wanted:
        return queued
    for v in db.list_videos(status="draft"):
        key = v["category"] or "longform"
        if key in wanted:
            try:
                publisher.enqueue(v["id"], now=now)
                queued.append(v["id"])
            except (publisher.ValidationError, ValueError) as e:
                db.update_video(v["id"], error=f"자동 대기열 제외: {e}")
    return queued


def last_tick() -> str | None:
    with db.connect() as c:
        r = c.execute("SELECT value FROM kv WHERE key='last_tick'").fetchone()
    return r["value"] if r else None


class Worker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="publisher-worker")
        self._stop_evt = threading.Event()

    def run(self):
        while not self._stop_evt.is_set():
            try:
                run_once()
            except Exception:
                db.log("error", "작업자 오류: " + traceback.format_exc(limit=3))
            self._stop_evt.wait(TICK_SECONDS)

    def stop(self):
        self._stop_evt.set()
