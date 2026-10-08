"""예약 슬롯 계산. 하루 N편(config upload.slots)을 지정 시각에 공개하도록 publishAt을 만든다."""
import datetime as dt
from zoneinfo import ZoneInfo


def next_slots(n: int, slots: list, tz: str, now: dt.datetime | None = None,
               taken: set | None = None, min_lead_min: int = 30) -> list:
    """앞으로 비어 있는 슬롯 n개를 RFC3339 문자열로 반환.
    now보다 min_lead_min분 이상 미래여야 하고, taken(이미 예약된 시각)은 건너뛴다."""
    zone = ZoneInfo(tz)
    now = (now or dt.datetime.now(zone)).astimezone(zone)
    earliest = now + dt.timedelta(minutes=min_lead_min)
    taken = taken or set()
    times = sorted(dt.datetime.strptime(s, "%H:%M").time() for s in slots)
    out, day = [], now.date()
    while len(out) < n:
        for t in times:
            cand = dt.datetime.combine(day, t, tzinfo=zone)
            iso = cand.isoformat()
            if cand >= earliest and iso not in taken:
                out.append(iso)
                if len(out) == n:
                    break
        day += dt.timedelta(days=1)
    return out
