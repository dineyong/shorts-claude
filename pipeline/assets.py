"""③ 비주얼 소스 확보: 보유 짤(meme_dir) 우선, 스톡은 Pixabay API(없으면 Pexels).
짤은 저작권/초상권 문제가 없는 것만 meme_dir에 직접 넣어 관리한다."""
import base64
import hashlib
import json
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


def pixabay_candidates(queries: list, cfg: dict, limit: int = 12) -> list:
    """검색어 여러 개로 후보를 모은다(중복·저품질 제외). 각 후보: id, tags, duration, thumb, url."""
    key = os.environ.get(cfg["assets"].get("pixabay_api_key_env", "PIXABAY_API_KEY"))
    if not key:
        return []
    seen, out = set(), []
    for q in queries:
        if not q:
            continue
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": key, "q": q[:100], "per_page": 8, "safesearch": "true"}, timeout=20)
        r.raise_for_status()
        for h in r.json().get("hits", []):
            v = h.get("videos", {})
            pick = v.get("medium") or v.get("large") or v.get("small") or v.get("tiny")
            if h["id"] in seen or h.get("isLowQuality") or not pick or not pick.get("url") or h.get("duration", 0) < 2:
                continue
            seen.add(h["id"])
            out.append({"id": h["id"], "tags": h.get("tags", ""), "duration": h.get("duration"),
                        "thumb": pick.get("thumbnail"), "url": pick["url"], "q": q})
            if len(out) >= limit:
                return out
    return out


def judge_candidates(scene: dict, cands: list, cfg: dict):
    """후보 썸네일을 Claude에게 보여 주고, 장면 내용에 가장 맞는 것을 고르게 한다.
    반환: (후보 index 또는 None, 이유). 맞는 게 없으면 None."""
    import anthropic
    content, idx = [], []
    for n, c in enumerate(cands):
        try:
            img = requests.get(c["thumb"], timeout=20).content
        except Exception:
            continue
        idx.append(n)
        content.append({"type": "text", "text": f"[{n}] tags: {c['tags'][:80]}"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(img).decode()}})
    if not content:
        return None, "썸네일 없음"
    vis = scene.get("visual", {})
    content.append({"type": "text", "text": (
        f"쇼츠 한 장면의 배경 영상을 고른다.\n대사: {scene['text']}\n"
        f"화면에 보여야 할 것: {vis.get('show') or vis.get('query')}\n"
        "위 후보 중 이 대사 순간에 가장 자연스럽게 어울리는 하나를 고른다.\n"
        "기준: (1) 대사/설명하는 대상과 실제로 관련 있을 것 (2) 만화·일러스트·무관한 인물/사물은 제외 "
        "(3) 세로로 중앙 크롭해도 피사체가 남을 것 (4) 실제 서비스·브랜드 로고(페이스북 등)가 또렷이 보이는 영상은 가급적 제외. 어울리는 게 하나도 없으면 null.\n"
        '출력은 JSON 한 줄만: {"best": 번호 또는 null, "reason": "한 문장"}')})
    msg = anthropic.Anthropic().messages.create(
        model=cfg["llm"]["model"], max_tokens=4000,
        messages=[{"role": "user", "content": content}])
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = text.removeprefix("```json").removesuffix("```").strip()
    try:
        d = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception:
        return None, f"판정 파싱 실패: {text[:60]}"
    best = d.get("best")
    return (best if isinstance(best, int) and best in idx else None), d.get("reason", "")


def pick_pixabay(scene: dict, cfg: dict, workdir: pathlib.Path, exclude: set = frozenset(),
                 cache_dir: pathlib.Path = pathlib.Path("cache/assets")):
    """장면에 맞는 Pixabay 영상을 고른다. 같은 대사+검색어는 캐시. 못 고르면 (None, 이유)."""
    vis = scene.get("visual", {})
    queries = [vis.get("query")] + list(vis.get("alt_queries") or [])
    key = hashlib.sha256(json.dumps([scene["text"], queries, sorted(exclude)], ensure_ascii=False).encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{key}.json"
    if cf.exists():
        d = json.loads(cf.read_text(encoding="utf-8"))
    else:
        cands = [c for c in pixabay_candidates(queries, cfg, limit=16) if c["id"] not in exclude][:12]
        if not cands:
            return None, "후보 없음"
        best, reason = judge_candidates(scene, cands, cfg)
        d = {"reason": reason, "pick": cands[best] if best is not None else None, "n": len(cands)}
        cf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if not d["pick"]:
        return None, f"맞는 영상 없음({d['n']}개 중): {d['reason']}"
    out = workdir / f"pixabay_{d['pick']['id']}.mp4"
    if not out.exists():
        out.write_bytes(requests.get(d["pick"]["url"], timeout=60).content)
    return str(out), d["reason"]


def resolve(scenes: list, cfg: dict, workdir: pathlib.Path) -> list:
    report, used = [], set()   # used: 한 영상 안에서 같은 클립 재사용 방지
    for n, sc in enumerate(scenes):
        vis = sc.get("visual", {"type": "text"})
        path, why = None, ""
        if vis["type"] == "meme":
            path = pick_meme(vis.get("query", ""), cfg["assets"]["meme_dir"])
        if path is None and vis["type"] in ("stock", "meme"):
            path, why = pick_pixabay(sc, cfg, workdir, exclude=frozenset(used))
            if path:
                used.add(int(pathlib.Path(path).stem.split('_')[1]))
            if path is None and not os.environ.get(cfg["assets"].get("pixabay_api_key_env", "PIXABAY_API_KEY")):
                path = fetch_pexels(vis.get("query", "funny"), cfg, workdir)   # Pixabay 키가 없을 때만 폴백
        if path is None and vis["type"] in ("stock", "meme") and n > 0 and scenes[n - 1].get("media"):
            path, why = scenes[n - 1]["media"], (why + " → 이전 장면 영상을 이어 씀")   # 단색 배경보다 낫다
        sc["media"] = path  # None이면 단색 배경 + 자막
        if vis["type"] in ("stock", "meme"):
            report.append({"scene": n, "text": sc["text"], "media": path, "why": why})
            print(f"      장면 {n}: {'OK ' if path else '없음'} {why[:60]}")
    (workdir / "visuals.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return scenes
