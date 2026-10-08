"""⑤ 유튜브 업로드(공식 Data API). 최초 1회 OAuth(client_secret.json 필요)."""
import pathlib
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload(video: pathlib.Path, meta: dict, cfg: dict, publish_at: str | None = None):
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    yt = build("youtube", "v3", credentials=flow.run_local_server(port=0))
    status = {"privacyStatus": cfg["upload"]["privacy"], "selfDeclaredMadeForKids": False}
    if publish_at:                      # RFC3339, 예: 2026-10-10T09:00:00+09:00
        status.update(privacyStatus="private", publishAt=publish_at)
    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta.get("description", "") + "\n#Shorts",
            "tags": meta.get("tags", []),
            "categoryId": "22",
        },
        "status": status,
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), resumable=True))
    return req.execute()
