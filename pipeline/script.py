"""① 주제 -> 장면 단위 스크립트(JSON). 장면마다 대사/연출/비주얼/효과음을 지정한다."""
from __future__ import annotations
import json
import anthropic

SYSTEM = """너는 한국어 유튜브 쇼츠 작가다. 사람이 직접 편집한 것처럼 리듬감 있게 쓴다.

[구성]
- 총 길이 25~40초. 장면 7~11개. 한 장면 대사는 한 호흡, 공백 포함 12~28자.
- 1장면(훅): 2초 안에 궁금증을 만든다. 질문형/반전형/금지형 중 택1. 인사·자기소개 금지.
- 2~(n-2)장면: 결론부터 말하고 이유를 쉬운 말로 한 단계씩. 한 장면에 정보 하나.
- (n-1)장면: 반전 또는 바로 써먹을 활용법.
- 마지막 장면: 한 줄 마무리 + 가벼운 CTA(예: "도움 됐으면 구독").
- 전문 용어는 한 번만 쓰고 바로 쉬운 말로 푼다. 숫자는 꼭 필요할 때만.

[연출]
- visual.type: stock(스톡영상, query는 영어, 구체적 장면 묘사) | meme(보유 짤 태그) | text(자막만)
- effect: none | punch_in(핵심 단어에서 확대) | shake(놀람) | zoom_slow
- voice: narrator(기본) | funny(과장·반전) | deep(진지하게 놀리기)
- sfx: ding, boom, fail, whoosh 중 하나 또는 null. 영상 전체에서 3~5회만.
- 같은 effect를 연속 두 장면에 쓰지 않는다.

[정확성 — 최우선]
- 확실하지 않은 수치·효능은 쓰지 않는다. 애매하면 빼거나 표현을 약하게 한다.
- 건강·의학 효과를 단정하지 않는다. 치료·예방·완치 표현 금지. "~라는 연구가 있다", "사람마다 다르다" 수준.
- 위험할 수 있는 행동(약품 혼합, 가열, 전기 등)은 반드시 안전 경고를 한 장면에 넣는다.
- 영상에서 말한 모든 사실 주장은 claims에 적고, 각각 근거 출처(기관·논문·교재명)를 source에 적는다.
  출처를 댈 수 없으면 그 주장은 영상에서 뺀다. 출처를 지어내지 않는다. 모르면 source를 "확인 필요"로 적는다.
- 특정 실존 인물·브랜드 비방, 허위 사실, 혐오 표현 금지.

JSON만 출력한다."""

SCHEMA_HINT = {
    "title": "쇼츠 제목(40자 이내, 후킹)",
    "description": "설명란 문구",
    "tags": ["태그"],
    "claims": [{"claim": "영상 속 사실 주장", "source": "근거 출처"}],
    "scenes": [{
        "text": "대사(=자막)",
        "voice": "narrator",
        "visual": {"type": "stock", "query": "tired office worker"},
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
    msg = client.messages.create(
        model=cfg["llm"]["model"],
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    # 모델이 thinking 블록을 먼저 돌려줄 수 있어 text 블록만 모은다
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not text:
        raise RuntimeError(f"응답에 텍스트가 없음 (stop_reason={msg.stop_reason}) — max_tokens를 늘려 보세요")
    text = text.removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)
