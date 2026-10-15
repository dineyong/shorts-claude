"""모의 유튜브 클라이언트(데모 모드/테스트). 실제 업로드는 하지 않고, 그럴듯한 통계를 만든다."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
from . import config
from .errors import PublishError

STATE = lambda: config.DATA_DIR / "mock_state.json"


def _load() -> dict:
    p = STATE()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save(d: dict) -> None:
    STATE().write_text(json.dumps(d), encoding="utf-8")


class MockClient:
    def __init__(self, channel_id: str = "default", fail_next: int = 0, authorized: bool = True, now=None):
        self.channel_id = channel_id
        self.now = now                    # 테스트용 고정 시각. None 이면 실제 시각
        self.fail_next = fail_next
        self._authorized = authorized

    def authorized(self) -> bool:
        return self._authorized

    def upload(self, path: str, body: dict, part: str, progress=None) -> str:
        if not self._authorized:
            from .errors import NotAuthorized
            raise NotAuthorized()
        if self.fail_next > 0:
            self.fail_next -= 1
            raise PublishError("모의 업로드 실패", retry_minutes=1)
        vid = "MOCK" + hashlib.sha1((path + body["snippet"]["title"]).encode()).hexdigest()[:7]
        st = _load()
        st[vid] = body["status"]["publishAt"]
        _save(st)
        if progress:
            progress(1.0)
        return vid

    def stats(self, ids: list, now: dt.datetime | None = None) -> dict:
        now = now or self.now or dt.datetime.now(dt.timezone.utc)
        st, out = _load(), {}
        for i in ids:
            if i not in st:
                out[i] = {"exists": False}
                continue
            at = dt.datetime.fromisoformat(st[i])
            hours = (now - at).total_seconds() / 3600
            if hours < 0:
                out[i] = {"exists": True, "privacy": "private", "views": 0, "likes": 0, "comments": 0}
                continue
            seed = int(hashlib.sha1(i.encode()).hexdigest()[:6], 16)
            peak = 800 + seed % 40000                       # 영상마다 최종 조회수 규모가 다름
            views = int(peak * (1 - math.exp(-hours / 36)))
            out[i] = {"exists": True, "privacy": "public", "views": views,
                      "likes": int(views * (0.03 + (seed % 7) / 200)),
                      "comments": int(views * 0.002)}
        return out
