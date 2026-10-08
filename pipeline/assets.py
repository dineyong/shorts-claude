"""③ 비주얼 소스 확보: 보유 짤(meme_dir) 우선, 스톡은 Pixabay API(없으면 Pexels).
짤은 저작권/초상권 문제가 없는 것만 meme_dir에 직접 넣어 관리한다."""
import os
import random
import pathlib
import requests

MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".webm"}


def pick_meme(tag: str, meme_dir: str):
    d = pathlib.Path(meme_dir) / tag
    files = [p for p in d.glob("*") if p.suffix.lower() in MEDIA_EXT] if d.exists() else []
    return str(random.choice(files)) if files else None


def fetch_pexels(query: str, cfg: dict, workdir: pathlib.Path):
    key = os.environ.get(cfg["assets"]["pexels_api_key_env"])
    if not key:
        return None
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": key},
        params={"query": query, "orientation": "portrait", "per_page": 5},
        timeout=20,
    )
    r.raise_for_status()
    videos = r.json().get("videos", [])
    if not videos:
        return None
    v = random.choice(videos)
    # 1080 폭에 가까운 mp4 파일 선택
    files = [f for f in v["video_files"] if f.get("file_type") == "video/mp4"]
    files.sort(key=lambda f: abs((f.get("width") or 0) - 1080))
    out = workdir / f"pexels_{v['id']}.mp4"
    if not out.exists():
        out.write_bytes(requests.get(files[0]["link"], timeout=60).content)
    return str(out)


def fetch_pixabay(query: str, cfg: dict, workdir: pathlib.Path):
    """Pixabay 영상 검색. 세로 영상 필터가 없어서 가로 클립도 오며, edit.py가 중앙 크롭한다."""
    key = os.environ.get(cfg["assets"].get("pixabay_api_key_env", "PIXABAY_API_KEY"))
    if not key:
        return None
    r = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": key, "q": query[:100], "per_page": 5, "safesearch": "true"},
        timeout=20,
    )
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if not hits:
        return None
    h = random.choice(hits)
    vids = h.get("videos", {})
    pick = vids.get("medium") or vids.get("large") or vids.get("small") or vids.get("tiny")
    if not pick or not pick.get("url"):
        return None
    out = workdir / f"pixabay_{h['id']}.mp4"
    if not out.exists():
        out.write_bytes(requests.get(pick["url"], timeout=60).content)
    return str(out)


def resolve(scenes: list, cfg: dict, workdir: pathlib.Path) -> list:
    for sc in scenes:
        vis = sc.get("visual", {"type": "text"})
        path = None
        if vis["type"] == "meme":
            path = pick_meme(vis.get("query", ""), cfg["assets"]["meme_dir"])
        if path is None and vis["type"] in ("stock", "meme"):
            q = vis.get("query", "funny")
            path = fetch_pixabay(q, cfg, workdir) or fetch_pexels(q, cfg, workdir)
        sc["media"] = path  # None이면 단색 배경 + 자막
    return scenes
