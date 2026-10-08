"""⑤ 유튜브 업로드(공식 Data API v3). 최초 1회 OAuth(client_secret.json 필요), 이후 token.json 재사용.
- 파일 지문으로 중복 업로드 차단, publishAt 예약, 재시도(지수 백오프), dry-run 지원
- 설정 방법은 docs/YOUTUBE_SETUP.md"""
from __future__ import annotations
import pathlib
import random
import time

from pipeline import ledger

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
RETRIABLE = {500, 502, 503, 504}
TOKEN = pathlib.Path("token.json")
SECRET = pathlib.Path("client_secret.json")


def _clean_title(t: str) -> str:
    t = t.replace("<", "").replace(">", "").strip()
    return t[:100]


def _clean_tags(tags: list) -> list:
    out, total = [], 0
    for tag in tags or []:
        tag = tag.replace("<", "").replace(">", "").replace(",", "").strip().lstrip("#")
        if tag and total + len(tag) <= 450:   # 전체 500자 제한 여유
            out.append(tag)
            total += len(tag)
    return out


def build_body(meta: dict, cfg: dict, publish_at: str | None = None) -> dict:
    """업로드 요청 본문(순수 함수 — 테스트 가능)."""
    up = cfg["upload"]
    desc = (meta.get("description", "").strip() + "\n\n#Shorts").strip()
    desc = desc.replace("<", "").replace(">", "")
    while len(desc.encode("utf-8")) > 4900:      # 5000바이트 제한
        desc = desc[:-10]
    status = {
        "privacyStatus": up.get("privacy", "private"),
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": bool(up.get("contains_synthetic_media", False)),
    }
    if publish_at:                      # 예약은 private 상태에서만 가능
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    return {
        "snippet": {
            "title": _clean_title(meta["title"]),
            "description": desc,
            "tags": _clean_tags(meta.get("tags", [])),
            "categoryId": str(up.get("category_id", "27")),   # 27=교육
            "defaultLanguage": "ko",
        },
        "status": status,
    }


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not SECRET.exists():
                raise SystemExit("client_secret.json 이 없습니다. docs/YOUTUBE_SETUP.md 참고")
            creds = InstalledAppFlow.from_client_secrets_file(str(SECRET), SCOPES).run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload(video, meta: dict, cfg: dict, publish_at: str | None = None, dry_run: bool = False) -> dict:
    video = pathlib.Path(video)
    fp = ledger.fingerprint(video)
    prev = ledger.already_uploaded(fp)
    if prev:
        print(f"이미 업로드된 영상입니다 (id={prev.get('video_id')}) — 건너뜀")
        return {"skipped": True, **prev}

    body = build_body(meta, cfg, publish_at)
    if dry_run:
        print("[dry-run] 업로드하지 않음. 요청 본문:")
        import json
        print(json.dumps(body, ensure_ascii=False, indent=2))
        return {"dry_run": True, "body": body}

    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    yt = get_service()
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    resp, retries = None, 0
    while resp is None:
        try:
            _, resp = req.next_chunk()
        except HttpError as e:
            if e.resp.status in RETRIABLE and retries < 8:
                retries += 1
                time.sleep(min(2 ** retries + random.random(), 60))
                continue
            raise
    entry = {"video_id": resp["id"], "title": body["snippet"]["title"],
             "publish_at": publish_at, "privacy": body["status"]["privacyStatus"],
             "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    ledger.record(fp, entry)
    print(f"업로드 완료: https://youtube.com/shorts/{resp['id']}  (공개 예약: {publish_at or body['status']['privacyStatus']})")
    return entry
