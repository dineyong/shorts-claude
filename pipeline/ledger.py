"""업로드 이력 장부. 파일 내용 지문(sha256)으로 같은 영상의 중복 업로드를 막고,
예약된 시각을 기록해 슬롯이 겹치지 않게 한다. 파일명을 바꿔도 중복으로 잡힌다."""
import hashlib
import json
import pathlib

LEDGER = pathlib.Path("state/upload_log.json")


def fingerprint(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: pathlib.Path = LEDGER) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"videos": {}}


def save(data: dict, path: pathlib.Path = LEDGER):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def already_uploaded(fp: str, path: pathlib.Path = LEDGER):
    return load(path)["videos"].get(fp)


def record(fp: str, entry: dict, path: pathlib.Path = LEDGER):
    data = load(path)
    data["videos"][fp] = entry
    save(data, path)


def taken_slots(path: pathlib.Path = LEDGER) -> set:
    return {v["publish_at"] for v in load(path)["videos"].values() if v.get("publish_at")}
