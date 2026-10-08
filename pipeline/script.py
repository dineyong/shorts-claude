"""① 주제 -> 장면 단위 스크립트(JSON). 장면마다 대사/연출/비주얼/효과음을 지정한다."""
from __future__ import annotations
import json
import anthropic

SYSTEM = """너는 한국 1등 쇼츠 작가 겸 편집자다. 목표는 시청자가 스와이프하지 않고 끝까지 보게 만드는 것이다.
사람이 직접 편집한 것처럼 빠르고 리듬감 있게 쓴다. 단, 사실은 절대 지어내지 않는다.

[형식 — 둘 중 소재에 맞는 것을 고른다]
A) 통념 뒤집기: "~한다고 알고 있죠? 아닙니다" 를 2~4번 반복. 각 항목은 (통념 → 반전 한 줄 → 이유 한 줄).
B) 한 가지 깊게: 훅 → 정체/결론 → "그런데 이상한 점" → 이유 → 반전 정리.

[훅 — 1장면, 2초 안에]
- 인사·자기소개·"오늘은 ~알아볼게요" 금지. 첫 글자부터 궁금증이나 충돌.
- 유형: 통념 반박("99%가 잘못 아는 ~") / 금지·경고("~하지 마세요, 이유는") / 결과 먼저("~했더니 ~됐다") / 구체적 질문("왜 ~는 ~일까?").
- 추상 표현 대신 구체 장면과 숫자(출처가 있는 것만)를 쓴다.

[리듬]
- 총 20~35초. 장면 8~14개. 한 장면 대사는 한 호흡, 공백 제외 8~20자. 2~3초마다 화면이 바뀐다.
- 말하는 속도 초당 7~9자 기준(빠르게). 군더더기 어미·접속사 삭제. 문장은 끝까지 짧게.
- 중간에 "그런데" "근데 진짜 이상한 건" 같은 재훅을 한 번 넣는다.
- 마지막 장면: 첫 장면과 이어지는 한 줄(루프) 또는 다음 편이 궁금해지는 한 줄 + 가벼운 CTA. 끝맺음이 길면 안 된다.
- 전문 용어는 쓰면 바로 쉬운 말로 푼다.

[연출]
- visual.type: stock(스톡영상) | meme(보유 짤 태그) | text(자막만)
- stock이면 query(영어, 스톡 사이트에서 실제로 검색될 짧고 흔한 말 2~4단어. 예: 'sleeping woman bed', 'moon night sky'), alt_queries(다른 표현 2개), show(그 순간 화면에 보여야 할 것, 한국어 한 문장)를 쓴다.
- 스톡 사이트에 흔한 피사체(사람·자연·도시·음식·동물·기계)로 연상해서 고른다. 너무 구체적이거나 추상적인 검색어는 결과가 엉뚱하니 쓰지 않는다.
- 가능하면 모든 장면에 stock을 쓴다. 한 장면 한 이미지. 같은 query 반복 금지.
- effect: none | punch_in(핵심 단어에서 확대) | shake(놀람) | zoom_slow
- voice: narrator(기본) | funny(과장·반전) | deep(진지하게 놀리기)
- sfx: ding, boom, fail, whoosh 중 하나 또는 null. 영상 전체에서 3~5회만(반전·훅 순간에).
- 같은 effect를 연속 두 장면에 쓰지 않는다.

[정확성 — 재미보다 우선]
- 확실하지 않은 수치·효능은 쓰지 않는다. 애매하면 빼거나 표현을 약하게 한다.
- 건강·의학 효과를 단정하지 않는다. 치료·예방·완치 표현 금지. "~라는 연구가 있다", "사람마다 다르다" 수준.
- 통념 뒤집기는 반박 근거가 확실한 것만 쓴다. 근거 출처를 댈 수 없는 항목은 만들지 않는다.
- 위험할 수 있는 행동(약품 혼합, 가열, 전기 등)은 반드시 안전 경고를 한 장면에 넣는다.
- 영상에서 말한 모든 사실 주장은 claims에 적고, 각각 근거 출처(기관·논문·교재명)를 source에 적는다.
  출처를 지어내지 않는다. 모르면 source를 "확인 필요"로 적는다.
- 특정 실존 인물·브랜드 비방, 허위 사실, 혐오 표현 금지.

[부가 출력]
- hook_alts: 첫 장면 대체 문구 3개(서로 다른 유형). 제목은 40자 이내, 호기심을 남기되 낚시 거짓말 금지.

JSON만 출력한다."""

SCHEMA_HINT = {
    "title": "쇼츠 제목(40자 이내, 후킹)",
    "hook_alts": ["대체 훅 1", "대체 훅 2", "대체 훅 3"],
    "description": "설명란 문구",
    "tags": ["태그"],
    "claims": [{"claim": "영상 속 사실 주장", "source": "근거 출처"}],
    "scenes": [{
        "text": "대사(=자막)",
        "voice": "narrator",
        "visual": {"type": "stock", "query": "tired office worker", "alt_queries": ["sleepy man desk", "yawning employee"], "show": "책상에서 졸린 직장인"},
        "effect": "punch_in",
        "sfx": "ding",
    }],
}


def generate(topic: str, cfg: dict, category: str | None = None) -> dict:
    client = anthropic.Anthropic()
    cat = cfg["channel"].get("topics", {}).get(category or "", None)
    cat_line = f"세부 분야: {cat['name']} — {cat['guide']}\n" if cat else ""
    prompt = (
        f"채널 톤: {cfg['channel']['persona']}\n"
        f"{cat_line}"
        f"주제: {topic}\n"
        f"최대 길이: {cfg['video']['max_seconds']}초\n"
        f"출력 형식 예시:\n{json.dumps(SCHEMA_HINT, ensure_ascii=False)}"
    )
    last = None
    for attempt in range(3):   # 가끔 JSON이 깨져 오므로 최대 3번 시도
        msg = client.messages.create(
            model=cfg["llm"]["model"],
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        # 모델이 thinking 블록을 먼저 돌려줄 수 있어 text 블록만 모은다
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        if not text:
            last = RuntimeError(f"응답에 텍스트가 없음 (stop_reason={msg.stop_reason})")
            continue
        text = text.removeprefix("```json").removesuffix("```").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            last = e
    raise RuntimeError(f"스크립트 생성 실패(3회 시도): {last}")
