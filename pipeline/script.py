"""① 주제 -> 장면 단위 스크립트(JSON). 장면마다 대사/연출/비주얼/효과음을 지정한다."""
import json
import anthropic

SYSTEM = """너는 한국어 유튜브 쇼츠 작가다. 사람이 직접 편집한 것처럼 리듬감 있게 쓴다.
규칙:
- 첫 장면은 2초 안에 시선을 잡는 훅. 마지막은 반전/펀치라인 + 짧은 CTA.
- 장면은 6~12개, 한 장면 대사는 한 호흡(최대 25자 내외).
- 각 장면에 visual, effect, sfx, voice를 지정한다.
- visual.type: stock(스톡영상, query는 영어) | meme(보유 짤 태그) | text(자막만)
- effect: none | punch_in(확대 강조) | shake(흔들림) | zoom_slow
- voice: narrator | funny | deep
- sfx: 효과음 이름 또는 null (예: ding, boom, fail, whoosh)
- 특정 실존 인물 비방, 허위 사실, 혐오 표현 금지.
- 과학·생활 팁은 정확성이 최우선이다. 확실하지 않은 수치·효능은 쓰지 않는다.
- 건강·의학 효과를 단정하지 않는다("~에 좋다" 대신 "~라는 연구가 있다" 수준, 치료/예방 주장 금지).
- 영상에서 말한 사실 주장은 claims 배열에 모두 적고, 각각 근거 출처(논문/기관/자료명)를 source에 적는다.
  출처를 댈 수 없는 주장은 영상에서 뺀다.
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


def generate(topic: str, cfg: dict) -> dict:
    client = anthropic.Anthropic()
    prompt = (
        f"채널 톤: {cfg['channel']['persona']}\n"
        f"주제: {topic}\n"
        f"최대 길이: {cfg['video']['max_seconds']}초\n"
        f"출력 형식 예시:\n{json.dumps(SCHEMA_HINT, ensure_ascii=False)}"
    )
    msg = client.messages.create(
        model=cfg["llm"]["model"],
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    text = text.removeprefix("```json").removesuffix("```").strip()
    return json.loads(text)
