"""사용법: python main.py "주제 한 줄" [--upload]"""
import argparse
import datetime
import hashlib
import json
import pathlib
import yaml

from pipeline import script, tts, assets, edit, upload, ledger, schedule, package
from pipeline.env import load_env
from pipeline.validate import validate
from pipeline.variation import style_for, vary_scenes


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--category", choices=["science", "kitchen", "habit"], help="세부 분야")
    ap.add_argument("--regen", action="store_true", help="스크립트 캐시 무시하고 새로 생성")
    ap.add_argument("--facts-file", help="검증된 사실·출처 텍스트 파일. 지정하면 스크립트의 사실 주장을 이 범위로 제한")
    ap.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--script-only", action="store_true", help="스크립트만 생성해 검토")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config, encoding="utf-8"))
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    work = pathlib.Path("work") / stamp
    work.mkdir(parents=True, exist_ok=True)

    facts = pathlib.Path(args.facts_file).read_text(encoding="utf-8") if args.facts_file else None
    key = hashlib.sha256(f"{args.category}|{args.topic}|{facts or ''}".encode()).hexdigest()[:12]
    sc_cache = pathlib.Path("cache/script") / f"{key}.json"
    if sc_cache.exists() and not args.regen:
        data = json.loads(sc_cache.read_text(encoding="utf-8"))
        print("(스크립트 캐시 사용 — 새로 받으려면 --regen)")
    else:
        data = script.generate(args.topic, cfg, args.category, facts)
        sc_cache.parent.mkdir(parents=True, exist_ok=True)
        sc_cache.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (work / "script.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[1/4] 스크립트 생성: {data['title']}")
    problems = validate(data)
    for pr in problems:
        print("  ⚠", pr)
    if args.script_only:
        return

    style = style_for(data["title"])
    data["scenes"] = vary_scenes(data["scenes"], data["title"])
    print(f"      스타일: {style['name']} / 자막 {style['font_size']}px y={style['caption_y']}")
    data["scenes"] = tts.synthesize(data["scenes"], cfg, work)
    print("[2/4] TTS 완료")
    data["scenes"] = assets.resolve(data["scenes"], cfg, work)
    print("[3/4] 소스 확보 완료")

    out = pathlib.Path("out"); out.mkdir(exist_ok=True)
    video = edit.render(data["scenes"], cfg, out / f"{stamp}.mp4", style)
    print(f"[4/4] 렌더 완료: {video}")

    publish_at = None
    if cfg["upload"].get("mode") == "schedule":
        up = cfg["upload"]
        publish_at = schedule.next_slots(1, up["slots"], up["timezone"], taken=ledger.taken_slots())[0]
    print("수동 업로드용 메타:", package.write_package(video, data, publish_at))
    if args.upload and cfg["upload"]["enabled"]:
        upload.upload(video, data, cfg, publish_at=publish_at)
    elif args.upload:
        print("config.yaml 의 upload.enabled 가 false 라 업로드하지 않았습니다.")


if __name__ == "__main__":
    main()
