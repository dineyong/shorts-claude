"""이미 만든 영상을 업로드/점검한다.
  python tools/upload_cli.py --auth                         # OAuth만 수행(token.json 생성)
  python tools/upload_cli.py out/x.mp4 examples/sample_script.json --dry-run
  python tools/upload_cli.py out/x.mp4 work/<stamp>/script.json --slot   # 다음 빈 슬롯에 예약
  python tools/upload_cli.py --slots 6                      # 앞으로 6개 슬롯 미리보기"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import yaml
from pipeline import ledger, schedule, upload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("meta", nargs="?", help="script.json (title/description/tags)")
    ap.add_argument("--auth", action="store_true")
    ap.add_argument("--slots", type=int, help="다음 빈 슬롯 N개 출력")
    ap.add_argument("--slot", action="store_true", help="다음 빈 슬롯에 예약")
    ap.add_argument("--at", help="공개 시각 직접 지정(RFC3339)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    up = cfg["upload"]

    if a.slots:
        for s in schedule.next_slots(a.slots, up["slots"], up["timezone"], taken=ledger.taken_slots()):
            print(s)
        return
    if a.auth:
        upload.get_service()
        print("인증 완료: token.json 저장됨")
        return
    if not (a.video and a.meta):
        ap.error("video 와 meta 가 필요합니다")
    meta = json.load(open(a.meta, encoding="utf-8"))
    at = a.at
    if a.slot:
        at = schedule.next_slots(1, up["slots"], up["timezone"], taken=ledger.taken_slots())[0]
    upload.upload(a.video, meta, cfg, publish_at=at, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
