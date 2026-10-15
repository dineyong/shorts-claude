"""발행 전 점검. errors 가 있으면 발행 대기로 못 넘기고, warnings 는 알려만 준다."""
from __future__ import annotations
import pathlib
from . import config
from .catalog import valid_category


def validate_video(v: dict, settings: dict) -> tuple:
    errors, warns = [], []
    fmt, cat = v.get("format"), v.get("category")

    if fmt not in ("shorts", "longform"):
        errors.append("포맷은 쇼츠 또는 롱폼이어야 합니다")
    elif not valid_category(fmt, cat):
        errors.append("카테고리가 올바르지 않습니다")
    if fmt == "longform" and not settings["longform"]["enabled"]:
        errors.append("롱폼은 아직 비활성입니다 (설정에서 켜기 전까지 발행 불가)")

    title = (v.get("title") or "").strip()
    if not title:
        errors.append("제목이 비어 있습니다")
    if len(title) > 100:
        errors.append(f"제목이 {len(title)}자입니다 (최대 100자)")
    if "<" in title or ">" in title:
        errors.append("제목에 < > 를 쓸 수 없습니다")

    desc = v.get("description") or ""
    if len(desc.encode("utf-8")) > 4900:
        errors.append("설명이 너무 깁니다 (5000바이트 미만)")
    if "<" in desc or ">" in desc:
        warns.append("설명의 < > 는 업로드 시 제거됩니다")
    tags = v.get("tags") or []
    if sum(len(t) for t in tags) > 450:
        warns.append("태그 합계가 450자를 넘어 일부는 잘립니다")

    fp = pathlib.Path(v.get("file_path") or "")
    if not fp.exists():
        errors.append("영상 파일을 찾을 수 없습니다")
    elif fp.suffix.lower() not in config.VIDEO_EXT:
        errors.append(f"지원하지 않는 형식입니다 ({fp.suffix})")

    claims = v.get("claims") or []
    unchecked = [c for c in claims if not c.get("checked")]
    if unchecked:
        errors.append(f"사실 확인: 영상 속 주장 {len(unchecked)}개의 출처를 확인하고 체크해야 합니다 (잘못된 정보 방지)")
    if any(x.get("source") == "직접 보유 파일" for x in (v.get("sources") or [])):
        warns.append("직접 보유한 파일을 썼습니다. 사용권을 확인하세요")

    # ---- 카테고리별 규칙 ----
    if fmt == "shorts" and cat == "drama_movie" and not v.get("rights_confirmed"):
        errors.append("드라마/영화: 사용권·저작권 확인 체크가 필요합니다 (타인의 방송·영화 영상은 저작권 문제로 삭제·수익 제한될 수 있음)")
    if fmt == "shorts" and cat == "shopping":
        if v.get("affiliate"):
            kws = settings.get("disclosure_keywords", [])
            if not any(k in desc for k in kws):
                errors.append("쇼핑(제휴/광고): 설명에 대가 표시 문구가 필요합니다 (예: '제휴 링크이며 수수료를 받을 수 있습니다')")
        else:
            warns.append("쇼핑: 제휴·협찬·광고가 없다면 그대로 두세요. 있다면 '제휴/광고 포함'을 체크하세요")
    if v.get("synthetic"):
        warns.append("합성/변형 콘텐츠로 공개 표시됩니다")
    return errors, warns
