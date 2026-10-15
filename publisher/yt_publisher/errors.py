from __future__ import annotations
class PublishError(Exception):
    """업로드/조회 실패. retry_minutes 후 재시도, fatal 이면 바로 실패 처리."""
    def __init__(self, msg: str, retry_minutes: int | None = None, fatal: bool = False, count_attempt: bool = True):
        super().__init__(msg)
        self.retry_minutes = retry_minutes
        self.fatal = fatal
        self.count_attempt = count_attempt


class NotAuthorized(PublishError):
    def __init__(self, msg: str = "채널 로그인이 필요합니다 (설정 → 채널 연결)"):
        super().__init__(msg, retry_minutes=10, count_attempt=False)
