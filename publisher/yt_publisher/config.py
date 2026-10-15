"""경로 설정. 모든 사용자 데이터는 data 폴더 한 곳에 모인다(복사하면 그대로 이사 가능)."""
from __future__ import annotations
import os
import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = pathlib.Path(os.environ.get("YT_PUBLISHER_HOME", APP_DIR / "data")).resolve()
DB_PATH = DATA_DIR / "publisher.db"
UPLOAD_DIR = DATA_DIR / "uploads"          # 화면에서 올린 영상
INBOX_DIR = DATA_DIR / "inbox"             # 폴더에 넣어두면 읽어오는 영상
TOKEN_DIR = DATA_DIR / "tokens"            # 채널별 로그인 토큰 (절대 공유 금지)
SECRET_PATH = DATA_DIR / "client_secret.json"
WEB_DIR = APP_DIR / "web"
VIDEO_EXT = {".mp4", ".mov", ".webm", ".m4v"}


def ensure_dirs() -> None:
    from .catalog import FORMATS, SHORTS_CATEGORIES
    for d in (DATA_DIR, UPLOAD_DIR, TOKEN_DIR):
        d.mkdir(parents=True, exist_ok=True)
    for cat in SHORTS_CATEGORIES:
        (INBOX_DIR / "shorts" / cat).mkdir(parents=True, exist_ok=True)
    (INBOX_DIR / "longform").mkdir(parents=True, exist_ok=True)
