"""폴더/화면에서 영상 등록. 같은 영상은 파일명이 달라도 한 번만 등록한다(내용 지문)."""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import re
import time
from . import config, db
from .catalog import SHORTS_CATEGORIES


def fast_hash(path) -> str:
    """대용량(롱폼)도 빠르게: 크기 + 앞 8MB + 뒤 8MB 의 sha256."""
    p = pathlib.Path(path)
    size = p.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with open(p, "rb") as f:
        h.update(f.read(8 << 20))
        if size > (16 << 20):
            f.seek(-(8 << 20), os.SEEK_END)
            h.update(f.read(8 << 20))
    return h.hexdigest()


def _sidecar(video: pathlib.Path) -> dict:
    for cand in (video.with_suffix(".json"), video.parent / "script.json"):
        if cand.exists() and cand.name != "state.json":
            try:
                d = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    return d
            except Exception:
                pass
    return {}


def register(path, fmt: str, category: str | None, meta: dict | None = None) -> tuple:
    """(영상 id, 새로 등록됐는지). 이미 있으면 기존 id 와 False."""
    p = pathlib.Path(path)
    h = fast_hash(p)
    dup = db.find_by_hash(h)
    if dup:
        return dup["id"], False
    meta = meta or _sidecar(p)
    vid = db.add_video(
        format=fmt, category=category if fmt == "shorts" else None,
        title=(meta.get("title") or p.stem)[:100], description=meta.get("description", ""),
        tags=meta.get("tags", []), file_path=str(p), file_hash=h,
        affiliate=int(bool(meta.get("affiliate"))), rights_confirmed=int(bool(meta.get("rights_confirmed"))),
        synthetic=int(bool(meta.get("synthetic"))),
    )
    return vid, True


def scan_inbox() -> dict:
    """inbox/shorts/<카테고리>/ 와 inbox/longform/ 의 새 영상을 초안으로 등록."""
    added, skipped = [], 0
    targets = [("shorts", c, config.INBOX_DIR / "shorts" / c) for c in SHORTS_CATEGORIES]
    targets.append(("longform", None, config.INBOX_DIR / "longform"))
    for fmt, cat, folder in targets:
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in config.VIDEO_EXT:
                vid, new = register(f, fmt, cat)
                if new:
                    added.append(vid)
                else:
                    skipped += 1
    return {"added": added, "skipped": skipped}


def safe_name(name: str) -> str:
    name = pathlib.Path(name).name
    name = re.sub(r"[^\w.\-가-힣]+", "_", name)[:120] or "video.mp4"
    return f"{int(time.time())}_{name}"
