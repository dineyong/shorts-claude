"""편성표: 앞으로 N일의 슬롯 칸에 어떤 영상이 들어 있는지 계산."""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo
from . import db
from .schedule import norm

WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"]


def build(days: int = 7, now: dt.datetime | None = None) -> dict:
    s = db.get_settings()
    tz = ZoneInfo(s["timezone"])
    now = (now or dt.datetime.now(tz)).astimezone(tz)
    times = sorted(set(s["shorts"]["slots"]) | set(s["longform"]["slots"]))
    dates = [now.date() + dt.timedelta(days=i) for i in range(days)]
    placed = {}
    for v in db.list_videos():
        if v["publish_at"] and v["status"] in ("queued", "uploaded", "published"):
            at = dt.datetime.fromisoformat(norm(v["publish_at"], s["timezone"]))
            placed.setdefault((at.date(), at.strftime("%H:%M")), []).append(
                {"id": v["id"], "title": v["title"], "format": v["format"], "category": v["category"],
                 "status": v["status"], "at": at.isoformat(timespec="minutes")})
    out_days, used = [], set()
    for d in dates:
        cells = {}
        for t in times:
            hh, mm = map(int, t.split(":"))
            slot_dt = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
            cells[t] = {"videos": placed.get((d, t), []), "past": slot_dt < now}
            used.add((d, t))
        out_days.append({"date": d.isoformat(), "weekday": WEEKDAY[d.weekday()], "cells": cells})
    custom = [x for (d, t), vs in placed.items() if (d, t) not in used and d in dates for x in vs]
    custom.sort(key=lambda x: x["at"])
    return {"times": times, "days": out_days, "custom": custom, "timezone": s["timezone"]}
