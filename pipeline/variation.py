"""영상별 변주. 같은 템플릿 반복으로 보이지 않도록 시드 기반으로 스타일을 바꾼다.
시드는 제목/주제 해시라 같은 영상은 항상 같은 스타일(재현 가능)."""
import hashlib
import random

PALETTES = [
    {"name": "white_yellow", "text": "white", "accent": "#FFE23A", "stroke": "black"},
    {"name": "white_cyan",   "text": "white", "accent": "#3AE0FF", "stroke": "black"},
    {"name": "white_pink",   "text": "white", "accent": "#FF5FA2", "stroke": "black"},
    {"name": "yellow_white", "text": "#FFE23A", "accent": "white", "stroke": "black"},
]
CAPTION_Y = [1180, 1250, 1320]          # 자막 세로 위치 후보
FONT_SIZES = [76, 84, 92]
LAYOUTS = ["caption_low", "caption_mid"]


def style_for(seed_text: str) -> dict:
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    r = random.Random(seed)
    s = dict(r.choice(PALETTES))
    s.update(caption_y=r.choice(CAPTION_Y), font_size=r.choice(FONT_SIZES),
             layout=r.choice(LAYOUTS), seed=seed)
    return s


def vary_scenes(scenes: list, seed_text: str) -> list:
    """연속 동일 효과 방지 + 효과음 과다 방지(최대 5회)."""
    r = random.Random(seed_text)
    pool = ["punch_in", "zoom_slow", "shake", "none"]
    prev, sfx_n = None, 0
    for sc in scenes:
        eff = sc.get("effect", "none")
        if eff != "none" and eff == prev:
            sc["effect"] = r.choice([e for e in pool if e != prev])
        prev = sc["effect"]
        if sc.get("sfx"):
            sfx_n += 1
            if sfx_n > 5:
                sc["sfx"] = None
    return scenes
