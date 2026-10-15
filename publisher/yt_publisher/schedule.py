"""공개 예약 슬롯 계산. 같은 채널에서 이미 잡힌 시각은 건너뛴다."""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo


def norm(iso: str, tz: str) -> str:
    """어떤 오프셋의 ISO 문자열이든 설정 시간대 기준 문자열로 통일."""
    d = dt.datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=ZoneInfo(tz))
    return d.astimezone(ZoneInfo(tz)).isoformat(timespec="seconds")


def next_free_slot(slots: list, tz: str, taken: set, now: dt.datetime | None = None,
                   min_lead_min: int = 30) -> str:
    if not slots:
        raise ValueError("예약 시각(slots)이 비어 있습니다. 설정에서 추가하세요")
    zone = ZoneInfo(tz)
    now = (now or dt.datetime.now(zone)).astimezone(zone)
    earliest = now + dt.timedelta(minutes=min_lead_min)
    times = sorted(dt.datetime.strptime(s, "%H:%M").time() for s in slots)
    day = now.date()
    for _ in range(3650):
        for t in times:
            cand = dt.datetime.combine(day, t, tzinfo=zone)
            iso = cand.isoformat(timespec="seconds")
            if cand >= earliest and iso not in taken:
                return iso
        day += dt.timedelta(days=1)
    raise RuntimeError("빈 슬롯을 찾지 못했습니다")
