"""반자동 폴백: 자동 업로드가 막히거나 쓰기 싫을 때, 영상 옆에 복붙용 메타 파일을 만든다."""
import pathlib


def write_package(video, meta: dict, publish_at: str | None = None) -> pathlib.Path:
    video = pathlib.Path(video)
    txt = video.with_suffix(".upload.txt")
    lines = [
        f"제목: {meta['title']}",
        f"예약 공개: {publish_at or '(수동 선택)'}",
        "",
        "[설명]",
        meta.get("description", ""),
        "",
        "#Shorts",
        "",
        "[태그]",
        ", ".join(meta.get("tags", [])),
        "",
        "[출처/사실 확인용 claims]",
    ]
    for c in meta.get("claims", []):
        lines.append(f"- {c.get('claim')}  ← {c.get('source')}")
    txt.write_text("\n".join(lines), encoding="utf-8")
    return txt
