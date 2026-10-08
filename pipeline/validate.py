"""스크립트 JSON 사전 검수(오프라인). 렌더 전에 형식·안전 문제를 잡는다."""
import re

BANNED = ["완치", "치료", "예방된다", "100%", "무조건", "암에 좋", "만병"]
SFX_OK = {"ding", "boom", "fail", "whoosh", None}
EFFECTS = {"none", "punch_in", "shake", "zoom_slow"}


def validate(data: dict) -> list:
    out = []
    scenes = data.get("scenes", [])
    if not 7 <= len(scenes) <= 11:
        out.append(f"장면 수 {len(scenes)}개 (권장 7~11)")
    total = sum(len(s.get("text", "")) for s in scenes)
    if not 120 <= total <= 330:
        out.append(f"전체 글자 수 {total} (권장 120~330, 약 25~40초)")
    prev = None
    sfx_n = 0
    for i, s in enumerate(scenes, 1):
        n = len(s.get("text", ""))
        if not 6 <= n <= 32:
            out.append(f"{i}번 장면 대사 {n}자 (권장 12~28)")
        if s.get("effect", "none") not in EFFECTS:
            out.append(f"{i}번 장면 effect 값 오류: {s.get('effect')}")
        if s.get("effect") not in (None, "none") and s.get("effect") == prev:
            out.append(f"{i}번 장면 effect가 직전과 동일")
        prev = s.get("effect")
        if s.get("sfx") not in SFX_OK:
            out.append(f"{i}번 장면 sfx 값 오류: {s.get('sfx')}")
        sfx_n += 1 if s.get("sfx") else 0
        for w in BANNED:
            if w in s.get("text", ""):
                out.append(f"{i}번 장면 금지/위험 표현 '{w}'")
    if not 3 <= sfx_n <= 5:
        out.append(f"효과음 {sfx_n}회 (권장 3~5)")
    claims = data.get("claims", [])
    if not claims:
        out.append("claims 비어 있음 — 사실 주장과 출처 필요")
    for c in claims:
        src = (c.get("source") or "").strip()
        if not src:
            out.append(f"출처 없음: {c.get('claim')}")
        elif "확인 필요" in src:
            out.append(f"출처 확인 필요(사람이 검증): {c.get('claim')}")
    if not re.search(r"구독|좋아요|팔로우", scenes[-1].get("text", "") if scenes else ""):
        out.append("마지막 장면에 CTA 없음(권장)")
    return out
