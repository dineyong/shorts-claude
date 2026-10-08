# shorts-auto (초기 틀)

주제 한 줄 → 스크립트(LLM) → 웃긴 TTS → 짤/스톡 소스 → 편집(확대·흔들림·효과음·자막) → 렌더 → 유튜브 업로드

## 구조
- `config.yaml` 채널 톤, TTS 보이스 프리셋, 소스 경로
- `pipeline/script.py` 장면 단위 JSON 생성 (대사·비주얼·효과·효과음·보이스 지정)
- `pipeline/tts.py` edge-tts, 보이스별 rate/pitch로 웃긴 톤
- `pipeline/assets.py` 보유 짤 우선 → Pexels 세로 영상 폴백
- `pipeline/edit.py` MoviePy 2.x 편집
- `pipeline/upload.py` YouTube Data API (기본 비활성)
- `docs/ROADMAP.md` 목표·세션별 계획·진행률 (`python tools/progress.py`로 갱신)

## 시작
```
pip install -r requirements.txt
python tools/setup_keys.py   # 키를 물어보고 .env 를 만들어 줌
python main.py "월요일 아침 출근길 공감" --script-only   # 먼저 스크립트만 검토
python main.py "월요일 아침 출근길 공감"                 # 전체 렌더
```

## 직접 채워야 하는 것
1. `assets/fonts/` 한글 굵은 폰트 (Pretendard 등)
2. `assets/sfx/` 효과음 mp3 (ding, boom, fail, whoosh …) — 라이선스 확인된 것만
3. `assets/memes/<태그>/` 짤 — 사용권이 확실한 것만. 유행 밈은 방송사 캡처·타인 영상 무단 사용 시 저작권 문제 소지
4. 주제(`channel.niche`) 확정

## TODO (우선순위)
- [ ] 주제 확정 후 `persona`/프롬프트 튜닝
- [ ] 단어 단위 자막 하이라이트 (whisper 정렬)
- [ ] 트렌드 수집 모듈(`pipeline/topic.py`) — 뉴스/커뮤니티 이슈 → 주제 후보
- [ ] BGM 덕킹, 컷 전환 효과
- [ ] 예약 업로드 + 중복 방지 (bibl-shorts-automation의 방식 참고)
- [ ] 영상마다 다른 시각/편집 변주 (유튜브 반복·대량생산 콘텐츠 정책 대비)
