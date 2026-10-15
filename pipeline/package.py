"""반자동 폴백: 자동 업로드가 막히거나 쓰기 싫을 때, 영상 옆에 복붙용 메타 파일을 만든다."""
from __future__ import annotations
import json
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


LICENSES = {
    "pixabay": ("Pixabay", "Pixabay Content License (표기 불필요, 단독 재판매 금지, 로고·상표 영상 주의)"),
    "pexels": ("Pexels", "Pexels License (표기 불필요, 인물 비하·제품 보증 암시 금지)"),
}


def provenance(work, scenes: list) -> list:
    """장면별로 어떤 소스를 썼는지 기록(나중에 권리 문제가 생기면 근거가 된다)."""
    out = []
    for n, sc in enumerate(scenes):
        m = sc.get("media")
        if not m:
            continue
        stem = pathlib.Path(m).stem
        kind = stem.split("_")[0]
        if kind in LICENSES:
            site, lic = LICENSES[kind]
            sid = stem.split("_", 1)[1] if "_" in stem else ""
            out.append({"scene": n, "source": site, "id": sid, "license": lic})
        else:
            out.append({"scene": n, "source": "직접 보유 파일", "id": pathlib.Path(m).name,
                        "license": "직접 관리 (사용권 확인 필요)"})
    return out


def write_meta(video, data: dict, problems: list, work, cfg: dict, publish_at=None) -> pathlib.Path:
    """발행 사이트용 메타. 영상 옆에 <영상이름>.meta.json 으로 저장."""
    video = pathlib.Path(video)
    meta = {
        "title": data["title"], "description": data.get("description", ""), "tags": data.get("tags", []),
        "claims": data.get("claims", []), "problems": problems,
        "sources": provenance(work, data.get("scenes", [])),
        "synthetic": bool(cfg.get("upload", {}).get("contains_synthetic_media", False)),
        "hook_alts": data.get("hook_alts", []),
    }
    path = video.with_suffix(".meta.json")
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
