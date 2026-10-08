# 유튜브 업로드 설정 (S4)

## 공식 문서로 확인한 사실 (2026-10-09 기준, 변경될 수 있음)
- `videos.insert` 업로드는 **하루 100회**, 1회당 1 quota (업로드 전용 버킷). 하루 2편이면 여유.
  https://developers.google.com/youtube/v3/determine_quota_cost
- 문서에 *"Videos uploaded from unverified API projects are not restricted to private viewing mode."* 라고 적혀 있음.
  즉 **과거의 '미검증 프로젝트 = 비공개 고정' 규칙은 현재 문서에 없음.** 다만 *"크리에이터 계정 설정에 따라 일부 업로드는 private이 기본일 수 있다"* 는 문구도 있음.
  https://developers.google.com/youtube/v3/docs/videos/insert
  → **실제 테스트 업로드로 최종 확인 필요** (아래 4번).
- 할당량 추가 요청은 컴플라이언스 감사 폼을 거쳐야 함. 하루 2편 운영에는 필요 없음.
  https://support.google.com/youtube/contact/yt_api_form
- 예약 공개(`status.publishAt`)는 영상이 **private** 상태로 올라가야 하며, 문서에 형식 상세는 없음(코드는 RFC3339 사용).

## 1. 구글 클라우드 설정 (최초 1회, 직접)
1. https://console.cloud.google.com → 새 프로젝트 생성
2. "API 및 서비스 → 라이브러리"에서 **YouTube Data API v3** 사용 설정
3. "OAuth 동의 화면" 구성 (외부, 테스트 모드) → **테스트 사용자에 본인 구글 계정 추가**
4. "사용자 인증 정보 → OAuth 클라이언트 ID 만들기 → 데스크톱 앱" → JSON 다운로드
5. 파일명을 `client_secret.json` 으로 바꿔 프로젝트 루트에 두기 (**git에 올리지 말 것 — .gitignore 처리됨**)
- 참고: 동의 화면이 '테스트' 상태면 refresh token이 약 7일 후 만료될 수 있음. 만료되면 `--auth`를 다시 실행.

## 2. 인증
```
pip install -r requirements.txt
python tools/upload_cli.py --auth       # 브라우저가 열리면 업로드할 채널의 구글 계정으로 로그인
```

## 3. 사전 점검 (업로드 없이)
```
python tools/upload_cli.py --slots 6                                   # 앞으로 6개 공개 슬롯
python tools/upload_cli.py out/x.mp4 examples/sample_script.json --slot --dry-run
```

## 4. 테스트 업로드로 비공개 고정 여부 확인
짧은 테스트 영상 1개를 `--slot` 없이 올린 뒤 YouTube Studio에서 확인한다.
- `config.yaml` 에서 `upload.mode: now`, `privacy: unlisted` 로 두고 `python main.py ... --upload` (또는 upload_cli)
- 공개/일부공개로 올라가면 → 자동 게시 가능, `mode: schedule` 로 전환
- 강제로 private이 되면 → 계정 설정/프로젝트 검증 문제. 이 경우 `out/*.upload.txt` 메타를 복붙하는 **반자동 게시**로 운영하고, 감사 폼 제출 여부를 결정

## 5. 운영
- `upload.enabled: true` 로 바꾸고 `python main.py "주제" --category science --upload`
- 예약 슬롯은 `config.yaml`의 `upload.slots`(기본 12:30, 19:30 KST). 이미 예약된 시각은 `state/upload_log.json` 을 보고 건너뜀
- 같은 영상은 파일명을 바꿔도 다시 올라가지 않음(내용 지문)
- `contains_synthetic_media`(변경/합성 콘텐츠 공개)는 유튜브 최신 정책을 읽고 결정. TTS 내레이션만 쓰는 경우의 해석은 공식 도움말로 확인할 것
