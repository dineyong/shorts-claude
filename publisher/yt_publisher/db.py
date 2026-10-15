"""SQLite 저장소. 호출마다 연결을 열고 닫는다(스레드 안전, WAL)."""
from __future__ import annotations
import contextlib
import datetime as dt
import json
import sqlite3
from . import config
from .settings import merged

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  format TEXT NOT NULL,                 -- shorts | longform
  category TEXT,                        -- drama_movie | shopping | humor | science | NULL(롱폼)
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  tags TEXT DEFAULT '[]',
  file_path TEXT NOT NULL,
  file_hash TEXT,
  channel_id TEXT DEFAULT 'default',
  status TEXT NOT NULL DEFAULT 'draft',
  publish_at TEXT,                      -- ISO8601(+오프셋). 유튜브 예약 공개 시각
  youtube_id TEXT,
  affiliate INTEGER DEFAULT 0,          -- 제휴/광고 링크 포함(쇼핑)
  rights_confirmed INTEGER DEFAULT 0,   -- 사용권·저작권 확인(드라마/영화)
  synthetic INTEGER DEFAULT 0,          -- 합성/변형 콘텐츠 공개
  attempts INTEGER DEFAULT 0,
  next_attempt_at TEXT,
  error TEXT,
  claims TEXT DEFAULT '[]',             -- [{claim, source, checked}] 사실 주장과 사람이 확인했는지
  sources TEXT DEFAULT '[]',            -- 쓴 영상 소스와 라이선스 기록
  problems TEXT DEFAULT '[]',           -- 제작 단계 검수기가 남긴 경고
  created_at TEXT, updated_at TEXT, uploaded_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_videos_hash ON videos(file_hash) WHERE file_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_videos_status ON videos(status);
CREATE TABLE IF NOT EXISTS stat_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id INTEGER NOT NULL, captured_at TEXT NOT NULL,
  views INTEGER, likes INTEGER, comments INTEGER,
  FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_snap_video ON stat_snapshots(video_id, captured_at);
CREATE TABLE IF NOT EXISTS channels (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic TEXT NOT NULL, sub TEXT, category TEXT, script_only INTEGER DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running',   -- running | script_ready | done | failed
  log TEXT DEFAULT '', script_path TEXT, video_id INTEGER, error TEXT,
  created_at TEXT, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, level TEXT, msg TEXT
);
"""

VIDEO_FIELDS = {
    "format", "category", "title", "description", "tags", "file_path", "file_hash",
    "channel_id", "status", "publish_at", "youtube_id", "affiliate", "rights_confirmed",
    "synthetic", "attempts", "next_attempt_at", "error", "uploaded_at", "claims", "sources", "problems",
}
JSON_FIELDS = ("tags", "claims", "sources", "problems")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


@contextlib.contextmanager
def connect():
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    config.ensure_dirs()
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        have = {r["name"] for r in c.execute("PRAGMA table_info(videos)")}   # 이전 버전 DB 이전(마이그레이션)
        for col in ("claims", "sources", "problems"):
            if col not in have:
                c.execute(f"ALTER TABLE videos ADD COLUMN {col} TEXT DEFAULT '[]'")
        c.execute("INSERT OR IGNORE INTO channels(id,name,created_at) VALUES('default','기본 채널',?)", (now_iso(),))


# ---- settings ----
def get_settings() -> dict:
    with connect() as c:
        row = c.execute("SELECT value FROM kv WHERE key='settings'").fetchone()
    return merged(json.loads(row["value"]) if row else None)


def save_settings(new: dict) -> dict:
    cur = get_settings()
    from .settings import _deep_update
    _deep_update(cur, new)
    with connect() as c:
        c.execute("INSERT INTO kv(key,value) VALUES('settings',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (json.dumps(cur, ensure_ascii=False),))
    return cur


# ---- videos ----
def _row(r) -> dict:
    d = dict(r)
    for k in JSON_FIELDS:
        d[k] = json.loads(d.get(k) or "[]")
    return d


def _enc(f: dict) -> None:
    for k in JSON_FIELDS:
        if isinstance(f.get(k), (list, tuple)):
            f[k] = json.dumps(list(f[k]), ensure_ascii=False)


def add_video(**f) -> int:
    f.setdefault("created_at", now_iso())
    f["updated_at"] = f["created_at"]
    _enc(f)
    cols = ",".join(f)
    ph = ",".join("?" for _ in f)
    with connect() as c:
        cur = c.execute(f"INSERT INTO videos({cols}) VALUES({ph})", list(f.values()))
        return cur.lastrowid


def get_video(vid: int) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    return _row(r) if r else None


def find_by_hash(h: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM videos WHERE file_hash=?", (h,)).fetchone()
    return _row(r) if r else None


def list_videos(fmt: str | None = None, category: str | None = None, status: str | None = None) -> list:
    q, args = "SELECT * FROM videos WHERE 1=1", []
    for col, val in (("format", fmt), ("category", category), ("status", status)):
        if val:
            q += f" AND {col}=?"
            args.append(val)
    q += " ORDER BY COALESCE(publish_at, created_at) DESC, id DESC"
    with connect() as c:
        return [_row(r) for r in c.execute(q, args).fetchall()]


def update_video(vid: int, **f) -> None:
    bad = set(f) - VIDEO_FIELDS
    if bad:
        raise ValueError(f"수정할 수 없는 필드: {bad}")
    _enc(f)
    f["updated_at"] = now_iso()
    sets = ",".join(f"{k}=?" for k in f)
    with connect() as c:
        c.execute(f"UPDATE videos SET {sets} WHERE id=?", [*f.values(), vid])


def delete_video(vid: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM videos WHERE id=?", (vid,))


# ---- snapshots ----
def add_snapshot(video_id: int, views: int, likes: int, comments: int, captured_at: str | None = None) -> None:
    with connect() as c:
        c.execute("INSERT INTO stat_snapshots(video_id,captured_at,views,likes,comments) VALUES(?,?,?,?,?)",
                  (video_id, captured_at or now_iso(), views, likes, comments))


def snapshots(video_id: int) -> list:
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM stat_snapshots WHERE video_id=? ORDER BY captured_at", (video_id,)).fetchall()]


# ---- channels / logs ----
def list_channels() -> list:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM channels ORDER BY created_at").fetchall()]


def add_channel(cid: str, name: str) -> None:
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO channels(id,name,created_at) VALUES(?,?,?)", (cid, name, now_iso()))


def log(level: str, msg: str) -> None:
    with connect() as c:
        c.execute("INSERT INTO logs(ts,level,msg) VALUES(?,?,?)", (now_iso(), level, msg))
        c.execute("DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 1000)")


def logs(limit: int = 100) -> list:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]


# ---- jobs (영상 제작 작업) ----
def add_job(topic: str, sub: str | None, category: str, script_only: bool) -> int:
    with connect() as c:
        return c.execute("INSERT INTO jobs(topic,sub,category,script_only,created_at) VALUES(?,?,?,?,?)",
                         (topic, sub, category, int(script_only), now_iso())).lastrowid


def get_job(jid: int) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    return dict(r) if r else None


def list_jobs(limit: int = 20) -> list:
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,topic,sub,category,script_only,status,video_id,error,created_at,finished_at FROM jobs ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()]


def update_job(jid: int, **f) -> None:
    sets = ",".join(f"{k}=?" for k in f)
    with connect() as c:
        c.execute(f"UPDATE jobs SET {sets} WHERE id=?", [*f.values(), jid])
