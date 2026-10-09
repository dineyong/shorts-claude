# shorts-claude — 유튜브 쇼츠 자동 제작 파이프라인

주제 한 줄을 넣으면 **Anthropic API(Claude)가 스크립트를 쓰고**, TTS로 읽고, 장면에 맞는 영상 소스를 고르고,
편집·렌더해서 쇼츠 영상 한 편을 만들고, 유튜브 업로드 준비(또는 예약 업로드)까지 하는 프로젝트입니다.
채널의 메인 주제는 **과학·생활 팁**이고, 목표는 하루 2편 운영으로 YPP Tier 1(구독자 500 + 90일 쇼츠 300만 조회 또는 시청 3,000시간)입니다.
목표·세션별 계획·진행률은 [docs/ROADMAP.md](docs/ROADMAP.md), 작업 기록은 [docs/WORKLOG.md](docs/WORKLOG.md)에 있습니다.

## 누가 무엇을 하나

| 맡은 일 | 담당 |
|---|---|
| 스크립트 작성, 소스 고르기, 편집·렌더, 코드·문서 관리, 자료 조사 | Claude (이 레포를 직접 수정하고 GitHub에 푸시) |
| 계정·결제·API 키 준비, OAuth 인증, 최종 게시 판단, 사람만 할 수 있는 확인 | 운영자(DINEYONG) |

## 전체 흐름

```
주제 한 줄
  ① Anthropic API(Claude)  → 장면 단위 스크립트 JSON (대사·연출·검색어·claims·출처)   pipeline/script.py
  ② 오프라인 검수기        → 길이·글자 수·금지 표현·출처 누락 점검                  pipeline/validate.py
  ③ TTS (edge-tts)         → 장면별 음성 mp3                                         pipeline/tts.py
  ④ 소스 고르기            → Pixabay 후보 12개를 Claude가 썸네일로 보고 하나 선택    pipeline/assets.py
  ⑤ 편집·렌더 (MoviePy)    → 효과·구절 자막·효과음·이어붙이기 → 1080x1920 mp4        pipeline/edit.py
  ⑥ 업로드 (YouTube API)   → 예약 슬롯 계산·중복 방지·dry-run·수동 업로드용 메타     pipeline/upload.py 외
```

## Anthropic API를 쓰는 곳 (2곳)

1. **스크립트 작성** — `pipeline/script.py`의 `generate()`
   - 모델: `config.yaml`의 `llm.model` (현재 `claude-sonnet-5-5`). 키는 환경변수 `ANTHROPIC_API_KEY`.
   - 시스템 프롬프트에 채널 작법을 넣습니다. 형식 두 가지(**통념 뒤집기** / **한 가지 깊게**), 훅 4유형(통념 반박·금지 경고·결과 먼저·구체적 질문),
     초당 7~9자 속도, 장면 8~14개, 중간 재훅, 루프형 마무리, 스톡 검색어 규칙.
   - 출력은 JSON 하나: 제목, **대체 훅 3개(`hook_alts`)**, 설명, 태그, **사실 주장과 출처(`claims`)**, 장면 목록
     (대사, 보이스, 비주얼 `query`/`alt_queries`/`show`, 효과, 효과음).
   - **정확성이 재미보다 우선**입니다. 출처를 대지 못하는 주장은 빼고, 모르면 `source`를 "확인 필요"로 적게 합니다.
     건강·의학 단정 표현 금지, 위험 행동은 안전 경고 장면 포함.
   - 응답에 thinking 블록이 먼저 올 수 있어 text 블록만 모읍니다. JSON이 깨져 오면 최대 3번 재시도합니다.
   - 같은 `(세부 분야, 주제)`는 `cache/script/`에 캐시합니다. 새로 받으려면 `--regen`.
2. **영상 소스 고르기** — `pipeline/assets.py`의 `judge_candidates()`
   - Pixabay에서 검색어 3개로 후보를 최대 12개 모으고, 후보 썸네일을 Claude(비전)에게 보여 대사와 가장 어울리는 하나를 고르게 합니다.
   - 만화·무관한 피사체·또렷한 브랜드 로고는 제외하고, 세로 중앙 크롭 후에도 피사체가 남는지 봅니다. 맞는 게 없으면 **억지로 고르지 않고** 단색 배경으로 둡니다.
   - 한 영상 안에서 같은 클립은 다시 쓰지 않습니다. 판정은 `cache/assets/`에 캐시되고, 장면별 이유는 `work/<시각>/visuals.json`에 남습니다.

## 시작하기

```bash
pip install -r requirements.txt
python3 tools/setup_keys.py                       # 키를 물어보고 .env 생성 (입력은 화면에 안 보임)
python3 main.py "주제 한 줄" --category habit --script-only   # 스크립트만 먼저 생성해 검토
python3 main.py "주제 한 줄" --category habit                 # 전체 렌더 (out/<시각>.mp4)
```

- `--category` 는 `science`(일상 속 과학 원리) / `kitchen`(주방·청소 꿀팁) / `habit`(습관·수면 상식).
- `--regen` 스크립트 캐시 무시, `--upload` 업로드(`config.yaml`의 `upload.enabled: true` 필요).
- ffmpeg는 `imageio-ffmpeg`(moviepy 의존성)에 포함된 것을 씁니다. Python 3.9(macOS 기본)에서 동작합니다.

### 필요한 키 (`.env`, git에 올라가지 않음)

| 키 | 용도 | 상태 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 스크립트 작성, 소스 고르기 | 설정됨 |
| `PIXABAY_API_KEY` | 스톡 영상 검색·다운로드 (1순위) | 설정됨 |
| `PEXELS_API_KEY` | 폴백. **Pexels는 신규 키 발급 중단 상태**라 기존 키가 있을 때만 | 미사용 |
| (예정) TTS 서비스 키 | 타입캐스트 또는 일레븐랩스 | 운영자 준비 필요 |

유튜브 업로드용 OAuth는 [docs/YOUTUBE_SETUP.md](docs/YOUTUBE_SETUP.md)를 따릅니다(사용자 인증이 필요해 아직 미연결).

## 폴더 구조

```
main.py                 진입점 (스크립트 → TTS → 소스 → 렌더 → 업로드 준비)
config.yaml             채널 톤, 세부 주제, TTS 보이스, 소스·업로드 설정
pipeline/
  script.py             ① Anthropic API 스크립트 작성
  validate.py           ② 오프라인 검수기
  tts.py                ③ edge-tts, 보이스 프리셋, 대사+보이스 해시 캐시
  assets.py             ④ 보유 짤 → Pixabay(Claude가 고름) → Pexels 폴백
  edit.py               ⑤ MoviePy 편집·렌더
  subtitle.py           구절 단위 자막과 글자 수 비례 타이밍
  variation.py          영상별 변주(팔레트·자막 위치·크기, 효과 중복 방지)
  upload.py, schedule.py, ledger.py, package.py   ⑥ 업로드·예약 슬롯·중복 방지·메타 패키지
  env.py                .env 로더
tools/                  setup_keys.py(키 입력), upload_cli.py(업로드), progress.py(진행률 막대)
tests/test_offline.py   오프라인 테스트 (API·네트워크 없이 실행)
examples/               샘플 스크립트
docs/                   ROADMAP, WORKLOG, RESEARCH, claims-review, YOUTUBE_SETUP
assets/                 (git 제외) fonts/ sfx/ memes/ — 직접 채움
cache/ work/ out/       (git 제외) 캐시·작업물·결과 영상
```

## 지키는 원칙

1. **사실 주장은 출처 필수.** 영상에서 말한 모든 사실은 `claims`에 근거와 함께 적고, 검수기가 "확인 필요"를 모두 표시합니다.
   표시가 남은 스크립트는 **사람이 확인하기 전에는 게시하지 않습니다.** (1차 검증표: [docs/claims-review.md](docs/claims-review.md))
2. **건강·의학은 단정하지 않습니다.** "~라는 연구가 있다", "사람마다 다르다" 수준.
3. **영상마다 변주합니다.** 같은 템플릿 반복 업로드는 유튜브의 반복·대량생산 콘텐츠 정책 위험이 있습니다.
4. **사용권 확인된 소스만 씁니다.** Pixabay 영상, 직접 확인한 짤·효과음·폰트만. 방송사 캡처·타인 영상은 쓰지 않습니다.
5. **조회수를 위해 사실을 부풀리지 않습니다.** 훅은 강하게, 내용은 사실 그대로.
6. 비밀키는 레포에 넣지 않습니다(`.env`는 gitignore).

## 현재 상태 (자세한 내용은 ROADMAP·WORKLOG)

- 스크립트 5개 생성·1차 출처 검증 완료. 지금 쓸 수 있는 건 폰 편뿐, 나머지 3편은 출처 보강 필요.
- Pixabay 연결과 **장면별 소스 고르기** 동작 확인(14장면 중 13장면 매칭).
- 렌더는 끝까지 동작하지만 **길이 45초(목표 20~35초)**: TTS가 느리고 장면마다 무음이 붙음 → 외부 TTS 교체 시 속도·무음 자르기 함께 처리 예정.
- 자막 폰트는 임시(맥 기본). Pretendard 등 사용권 확실한 폰트로 교체 예정.
- 유튜브 업로드는 코드 완료, OAuth 인증과 테스트 업로드 전.

## 직접 채워야 하는 것

1. `assets/fonts/` 한글 굵은 폰트 (Pretendard 등)
2. `assets/sfx/` 효과음 mp3 (ding, boom, fail, whoosh) — 사용권 확인된 것만
3. TTS 서비스 계정·키 (타입캐스트 또는 일레븐랩스)
4. 유튜브 OAuth 인증(최초 1회)

## 테스트

```bash
python3 tests/test_offline.py     # API·네트워크 없이 도는 테스트
```

## 참고 자료

- 잘되는 쇼츠 분석: [docs/RESEARCH.md](docs/RESEARCH.md)
- 참고한 오픈소스: bibl-shorts-automation, paper2video, MoneyPrinterTurbo, reddit-shorts (S0 단계에서 조사한 참고 대상)
