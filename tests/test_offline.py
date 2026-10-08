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

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
