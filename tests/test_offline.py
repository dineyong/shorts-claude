"""오프라인 단위 테스트: python tests/test_offline.py"""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from pipeline.subtitle import split_chunks, timings
from pipeline.variation import style_for, vary_scenes
from pipeline.validate import validate
from pipeline.tts import cache_path

def test_chunks():
    c = split_chunks("분명 안 끓는데 컵을 들면 확 터져요")
    assert all(len(x) <= 10 for x in c), c
    assert " ".join(c) == "분명 안 끓는데 컵을 들면 확 터져요"
    assert split_chunks("") == []
    assert split_chunks("초장문어절이열글자를넘어도쪼개지않는다 네") [0].startswith("초장문")

def test_timings():
    t = timings("물만 데우다 화상 입는 사람 많아요", 3.0)
    assert t[0][1] == 0 and t[-1][2] == 3.0
    assert all(t[i][2] == t[i+1][1] for i in range(len(t)-1))

def test_style_deterministic():
    assert style_for("제목") == style_for("제목")
    assert style_for("A")["seed"] != style_for("B")["seed"]

def test_vary():
    sc = [{"effect": "shake", "sfx": "ding"} for _ in range(8)]
    out = vary_scenes(sc, "x")
    assert all(out[i]["effect"] != out[i+1]["effect"] or out[i]["effect"] == "none" for i in range(7))
    assert sum(1 for s in out if s["sfx"]) <= 5

def test_cache_key():
    d = pathlib.Path(tempfile.mkdtemp())
    a = cache_path("안녕", {"name": "v", "rate": "+0%"}, d)
    assert a == cache_path("안녕", {"name": "v", "rate": "+0%"}, d)
    assert a != cache_path("안녕", {"name": "v", "rate": "+10%"}, d)

def test_sample_validates_structure():
    d = json.load(open(pathlib.Path(__file__).resolve().parent.parent / "examples/sample_script.json", encoding="utf-8"))
    issues = [x for x in validate(d) if "확인 필요" not in x]
    assert issues == [], issues


def test_schedule():
    import datetime as dt
    from zoneinfo import ZoneInfo
    from pipeline.schedule import next_slots
    z = ZoneInfo("Asia/Seoul")
    now = dt.datetime(2026, 10, 9, 13, 0, tzinfo=z)
    s = next_slots(3, ["12:30", "19:30"], "Asia/Seoul", now=now)
    assert s == ["2026-10-09T19:30:00+09:00", "2026-10-10T12:30:00+09:00", "2026-10-10T19:30:00+09:00"], s
    s2 = next_slots(2, ["12:30", "19:30"], "Asia/Seoul", now=now, taken={"2026-10-09T19:30:00+09:00"})
    assert s2[0] == "2026-10-10T12:30:00+09:00", s2
    # 최소 리드타임: 19:10이면 19:30 슬롯은 30분 미만이라 건너뜀
    s3 = next_slots(1, ["12:30", "19:30"], "Asia/Seoul", now=dt.datetime(2026, 10, 9, 19, 10, tzinfo=z))
    assert s3[0] == "2026-10-10T12:30:00+09:00", s3

def test_ledger_dedupe():
    from pipeline import ledger
    d = pathlib.Path(tempfile.mkdtemp())
    a, b = d / "a.mp4", d / "renamed.mp4"
    a.write_bytes(b"same-bytes"); b.write_bytes(b"same-bytes")
    assert ledger.fingerprint(a) == ledger.fingerprint(b)
    led = d / "log.json"
    assert ledger.already_uploaded(ledger.fingerprint(a), led) is None
    ledger.record(ledger.fingerprint(a), {"video_id": "X", "publish_at": "T"}, led)
    assert ledger.already_uploaded(ledger.fingerprint(b), led)["video_id"] == "X"
    assert ledger.taken_slots(led) == {"T"}

def test_build_body():
    import yaml
    from pipeline.upload import build_body
    cfg = yaml.safe_load(open(pathlib.Path(__file__).resolve().parent.parent / "config.yaml", encoding="utf-8"))
    meta = {"title": "가" * 120 + "<b>", "description": "설명", "tags": ["#과학", "a,b", "x" * 600]}
    body = build_body(meta, cfg, "2026-10-10T12:30:00+09:00")
    assert len(body["snippet"]["title"]) <= 100 and "<" not in body["snippet"]["title"]
    assert body["status"]["privacyStatus"] == "private" and body["status"]["publishAt"].startswith("2026-10-10")
    assert "#Shorts" in body["snippet"]["description"]
    assert sum(len(t) for t in body["snippet"]["tags"]) <= 500
    assert body["status"]["selfDeclaredMadeForKids"] is False
    now = build_body({"title": "t"}, cfg, None)
    assert "publishAt" not in now["status"]

def test_package():
    from pipeline.package import write_package
    d = pathlib.Path(tempfile.mkdtemp()); v = d / "v.mp4"; v.write_bytes(b"x")
    meta = json.load(open(pathlib.Path(__file__).resolve().parent.parent / "examples/sample_script.json", encoding="utf-8"))
    txt = write_package(v, meta, "2026-10-10T12:30:00+09:00")
    s = txt.read_text(encoding="utf-8")
    assert meta["title"] in s and "확인 필요" in s and "2026-10-10T12:30" in s

def test_env_loader():
    import os
    from pipeline.env import load_env
    d = pathlib.Path(tempfile.mkdtemp()); f = d / ".env"
    f.write_text('# c\nTEST_KEY_A="abc"\nTEST_KEY_B = xyz\n\nBAD LINE\n', encoding="utf-8")
    os.environ.pop("TEST_KEY_A", None); os.environ["TEST_KEY_B"] = "keep"
    load_env(str(f))
    assert os.environ["TEST_KEY_A"] == "abc" and os.environ["TEST_KEY_B"] == "keep"

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
