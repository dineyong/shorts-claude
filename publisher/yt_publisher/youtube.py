"""실제 유튜브 클라이언트(공식 Data API v3). google 라이브러리는 필요할 때만 불러온다."""
from __future__ import annotations
import json
import pathlib
import random
import time
from . import config
from .errors import NotAuthorized, PublishError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",   # 비공개/예약 영상 통계 조회
]
RETRIABLE = {500, 502, 503, 504}


def token_path(channel_id: str) -> pathlib.Path:
    return config.TOKEN_DIR / f"{channel_id}.json"


class YouTubeClient:
    def __init__(self, channel_id: str = "default"):
        self.channel_id = channel_id

    # ---- 인증 ----
    def authorized(self) -> bool:
        p = token_path(self.channel_id)
        if not p.exists():
            return False
        try:
            return bool(json.loads(p.read_text(encoding="utf-8")).get("refresh_token"))
        except Exception:
            return False

    def authorize(self) -> None:
        """브라우저 로그인 창을 열어 토큰을 저장한다(최초 1회)."""
        from google_auth_oauthlib.flow import InstalledAppFlow
        if not config.SECRET_PATH.exists():
            raise PublishError("client_secret.json 이 없습니다 (설정 → 구글 인증 파일 올리기)", fatal=True)
        creds = InstalledAppFlow.from_client_secrets_file(str(config.SECRET_PATH), SCOPES).run_local_server(port=0)
        config.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        token_path(self.channel_id).write_text(creds.to_json(), encoding="utf-8")

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        p = token_path(self.channel_id)
        if not p.exists():
            raise NotAuthorized()
        creds = Credentials.from_authorized_user_file(str(p), SCOPES)
        if not creds.valid:
            if creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:  # 테스트 모드 동의화면의 7일 만료 등
                    raise NotAuthorized(f"로그인이 만료되었습니다. 설정에서 채널을 다시 연결하세요 ({e})")
                p.write_text(creds.to_json(), encoding="utf-8")
            else:
                raise NotAuthorized()
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    # ---- 업로드 ----
    def upload(self, path: str, body: dict, part: str, progress=None) -> str:
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
        yt = self._service()
        try:
            return self._insert(yt, path, body, part, progress)
        except HttpError as e:
            reason = _reason(e)
            if "paidProductPlacementDetails" in part and e.resp.status == 400:
                # 이 part 를 받지 않는 경우: 빼고 다시 올리고, 스튜디오에서 직접 표시하도록 안내
                body = {k: v for k, v in body.items() if k != "paidProductPlacementDetails"}
                vid = self._insert(yt, path, body, "snippet,status", progress)
                from . import db
                db.log("warn", f"{vid}: 유료 광고 표시를 API로 설정하지 못했습니다. 유튜브 스튜디오에서 '유료 프로모션 포함'을 직접 체크하세요")
                return vid
            if e.resp.status == 403 and "quota" in reason.lower():
                raise PublishError("유튜브 API 일일 할당량 초과", retry_minutes=360)
            if e.resp.status in (401, 403):
                raise PublishError(f"권한 오류: {reason}", fatal=False, retry_minutes=30)
            raise PublishError(f"업로드 실패 ({e.resp.status}): {reason}", retry_minutes=15)

    def _insert(self, yt, path, body, part, progress):
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
        req = yt.videos().insert(part=part, body=body,
                                 media_body=MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True))
        resp, retries = None, 0
        while resp is None:
            try:
                status, resp = req.next_chunk()
                if status and progress:
                    progress(status.progress())
            except HttpError as e:
                if e.resp.status in RETRIABLE and retries < 8:
                    retries += 1
                    time.sleep(min(2 ** retries + random.random(), 60))
                    continue
                raise
        return resp["id"]

    # ---- 통계/상태 ----
    def stats(self, ids: list) -> dict:
        yt = self._service()
        out = {}
        for i in range(0, len(ids), 50):                     # videos.list 는 한 번에 최대 50개
            chunk = ids[i:i + 50]
            resp = yt.videos().list(part="statistics,status", id=",".join(chunk)).execute()
            found = set()
            for it in resp.get("items", []):
                s = it.get("statistics", {})
                found.add(it["id"])
                out[it["id"]] = {
                    "exists": True,
                    "privacy": it.get("status", {}).get("privacyStatus"),
                    "views": int(s.get("viewCount", 0)),
                    "likes": int(s.get("likeCount", 0)),       # 좋아요 수를 숨긴 영상은 0
                    "comments": int(s.get("commentCount", 0)),
                }
            for m in set(chunk) - found:
                out[m] = {"exists": False}
        return out


def _reason(e) -> str:
    try:
        return json.loads(e.content.decode("utf-8"))["error"]["errors"][0]["reason"]
    except Exception:
        return str(e)


def client_for(channel_id: str, settings: dict):
    if settings.get("mode") == "live":
        return YouTubeClient(channel_id)
    from .mock import MockClient
    return MockClient(channel_id)
