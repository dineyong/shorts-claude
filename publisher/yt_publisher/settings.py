"""설정 기본값과 병합. 저장은 DB(settings 테이블)에 JSON으로."""
from __future__ import annotations
import copy

DEFAULTS = {
    "timezone": "Asia/Seoul",
    "mode": "demo",                 # demo(모의, 실제 업로드 없음) | live(실제 유튜브)
    "min_lead_min": 30,             # 공개 예약은 현재+이 시간 이후만
    "daily_upload_cap": 20,         # 하루 업로드 상한(유튜브 API 한도는 별도로 100회)
    "stats_interval_min": 60,       # 통계 수집 주기
    "shorts_max_seconds": 180,      # 쇼츠 길이 경고 기준 (유튜브 최신 규정 확인 필요)
    "shorts": {
        "slots": ["08:30", "12:30", "18:30", "21:00"],
        "add_shorts_tag": True,     # 설명 끝에 #Shorts 자동 추가
    },
    "longform": {                   # 롱폼은 세팅만: enabled=False 면 등록/예약 불가
        "enabled": False,
        "slots": ["19:00"],
        "default_tags": [],
        "description_template": "",
        "min_minutes": 8,
    },
    "channel_map": {                # 카테고리 → 채널 id (채널 하나로 시작)
        "drama_movie": "default", "shopping": "default",
        "humor": "default", "science": "default", "longform": "default",
    },
    "yt_category_ids": {},          # 비어 있으면 catalog 기본값
    "disclosure_keywords": ["광고", "협찬", "제휴", "수수료", "파트너스"],
}


def merged(saved: dict | None) -> dict:
    out = copy.deepcopy(DEFAULTS)
    _deep_update(out, saved or {})
    return out


def _deep_update(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
