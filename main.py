"""사용법: python main.py "주제 한 줄" [--upload]"""
import argparse
import datetime
import json
import pathlib
import yaml

from pipeline import script, tts, assets, edit, upload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--script-only", action="store_true", help="스크립트만 생성해 검토")
    args = ap.parse_args()

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    work = pathlib.Path("work") / stamp
    work.mkdir(parents=True, exist_ok=True)

    data = script.generate(args.topic, cfg)
    (work / "script.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[1/4] 스크립트 생성: {data['title']}")
    if args.script_only:
        return

    data["scenes"] = tts.synthesize(data["scenes"], cfg, work)
    print("[2/4] TTS 완료")
    data["scenes"] = assets.resolve(data["scenes"], cfg, work)
    print("[3/4] 소스 확보 완료")

    out = pathlib.Path("out"); out.mkdir(exist_ok=True)
    video = edit.render(data["scenes"], cfg, out / f"{stamp}.mp4")
    print(f"[4/4] 렌더 완료: {video}")

    if args.upload and cfg["upload"]["enabled"]:
        print("업로드:", upload.upload(video, data, cfg).get("id"))


if __name__ == "__main__":
    main()
