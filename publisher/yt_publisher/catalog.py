"""분류 체계: 포맷(롱폼/쇼츠) → 카테고리. 롱폼은 세팅만 해두고 기본 비활성."""
from __future__ import annotations

FORMATS = {
    "shorts":   {"label": "쇼츠"},
    "longform": {"label": "롱폼"},
}

SHORTS_CATEGORIES = {
    "drama_movie": "드라마/영화",
    "shopping":    "쇼핑",
    "humor":       "유머",
    "science":     "과학",
}

# 유튜브 categoryId 기본값 (설정에서 바꿀 수 있음)
DEFAULT_YT_CATEGORY = {
    "drama_movie": "24",   # 엔터테인먼트
    "shopping":    "22",   # 인물/블로그
    "humor":       "23",   # 코미디
    "science":     "28",   # 과학기술
    "longform":    "27",   # 교육
}

STATUSES = ["draft", "queued", "uploaded", "published", "failed"]
STATUS_LABEL = {
    "draft": "초안", "queued": "발행 대기", "uploaded": "업로드됨(공개 예약)",
    "published": "공개됨", "failed": "실패",
}


def category_label(fmt: str, category: str | None) -> str:
    if fmt == "longform":
        return "롱폼"
    return SHORTS_CATEGORIES.get(category or "", category or "-")


def valid_category(fmt: str, category: str | None) -> bool:
    if fmt == "longform":
        return category in (None, "", "longform")
    return category in SHORTS_CATEGORIES
