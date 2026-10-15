"""유튜브 업로드 요청 본문 생성(순수 함수)."""
from __future__ import annotations
from .catalog import DEFAULT_YT_CATEGORY


def _strip_angle(s: str) -> str:
    return s.replace("<", "").replace(">", "")


def _fit_bytes(s: str, limit: int = 4900) -> str:
    while len(s.encode("utf-8")) > limit:
        s = s[:-1]
    return s


def clean_tags(tags: list) -> list:
    out, total = [], 0
    for t in tags or []:
        t = _strip_angle(str(t)).replace(",", "").strip().lstrip("#")
        if t and total + len(t) <= 450:
            out.append(t)
            total += len(t)
    return out


def build(video: dict, settings: dict) -> tuple:
    """(body, part) 반환. 항상 private + publishAt 으로 올려 시각에 공개되게 한다."""
    fmt, cat = video["format"], video.get("category")
    key = cat or "longform"
    desc = (video.get("description") or "").strip()
    tags = list(video.get("tags") or [])
    if fmt == "shorts" and settings["shorts"].get("add_shorts_tag") and "#shorts" not in desc.lower():
        desc = (desc + "\n\n#Shorts").strip()
    if fmt == "longform":
        tpl = settings["longform"].get("description_template", "")
        if tpl:
            desc = tpl.replace("{description}", desc) if "{description}" in tpl else (desc + "\n\n" + tpl).strip()
        tags += settings["longform"].get("default_tags", [])
    cat_id = (settings.get("yt_category_ids") or {}).get(key) or DEFAULT_YT_CATEGORY[key]
    body = {
        "snippet": {
            "title": _strip_angle(video["title"]).strip()[:100],
            "description": _fit_bytes(_strip_angle(desc)),
            "tags": clean_tags(tags),
            "categoryId": str(cat_id),
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": video["publish_at"],
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(video.get("synthetic")),
        },
    }
    part = "snippet,status"
    if video.get("affiliate"):
        body["paidProductPlacementDetails"] = {"hasPaidProductPlacement": True}
        part += ",paidProductPlacementDetails"
    return body, part
