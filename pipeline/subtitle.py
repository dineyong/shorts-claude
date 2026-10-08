"""자막 청크 분할과 타이밍. 대사를 짧은 구절로 쪼개 오디오 길이에 글자 수 비례로 배분한다.
(정확한 단어 싱크가 필요하면 whisper 정렬로 교체 — S3 후속)"""
import re

MAX_CHARS = 10          # 한 화면에 보여줄 구절 최대 글자 수(공백 제외 기준 아님, 가독성용)


def split_chunks(text: str, max_chars: int = MAX_CHARS) -> list:
    """어절 단위로 묶되 max_chars를 넘기지 않는다. 한 어절이 더 길어도 쪼개지 않는다."""
    words = re.split(r"\s+", text.strip())
    chunks, cur = [], ""
    for w in words:
        if not w:
            continue
        if cur and len(cur) + 1 + len(w) > max_chars:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def timings(text: str, duration: float, max_chars: int = MAX_CHARS) -> list:
    """[(chunk, start, end), ...] — 글자 수 비례. 마지막 청크는 duration까지 유지."""
    chunks = split_chunks(text, max_chars)
    if not chunks:
        return []
    weights = [max(len(c.replace(" ", "")), 1) for c in chunks]
    total = sum(weights)
    out, t = [], 0.0
    for c, w in zip(chunks, weights):
        d = duration * w / total
        out.append((c, round(t, 3), round(t + d, 3)))
        t += d
    out[-1] = (out[-1][0], out[-1][1], round(duration, 3))
    return out
