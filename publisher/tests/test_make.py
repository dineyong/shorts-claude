import importlib, json, pathlib, sqlite3, sys, tempfile, time, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from helpers import fresh_home, make_video

STUB = '''
import sys, json, pathlib
a = sys.argv
print("WORK_DIR=work/t1", flush=True)
w = pathlib.Path("work/t1"); w.mkdir(parents=True, exist_ok=True)
data = {"title": "테스트 제목", "claims": [{"claim": "주장1", "source": "확인 필요"}, {"claim": "주장2", "source": "교재"}], "scenes": []}
if "--script-file" in a:
    data = json.load(open(a[a.index("--script-file") + 1], encoding="utf-8")); print("(지정한 스크립트 파일 사용)")
(w / "script.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print("  ⚠ 출처 확인 필요(사람이 검증): 주장1")
if "--script-only" in a: sys.exit(0)
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
(out / "t1.mp4").write_bytes(b"fake-video" * 1000)
meta = {"title": data["title"], "description": "d", "tags": ["a"], "claims": data["claims"], "problems": [],
        "sources": [{"scene": 0, "source": "Pixabay", "id": "1", "license": "Pixabay Content License"}]}
(out / "t1.meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
print("RENDER_DONE=out/t1.mp4"); print("META=out/t1.meta.json")
'''


def wait(db, jid, n=100):
    for _ in range(n):
        j = db.get_job(jid)
        if j["status"] != "running":
            return j
        time.sleep(0.1)
    raise AssertionError("작업이 끝나지 않음")


class T(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        from yt_publisher import db, jobs, checks, publisher
        self.db, self.jobs, self.checks, self.pub = db, jobs, checks, publisher
        self.pd = pathlib.Path(tempfile.mkdtemp(prefix="pipe_"))
        (self.pd / "pipeline").mkdir()
        (self.pd / "main.py").write_text(STUB, encoding="utf-8")
        self.s = {**db.get_settings(), "pipeline_dir": str(self.pd)}

    def test_script_then_render_and_claims_gate(self):
        jid = self.jobs.start(self.s, "거북이", "science", "science", script_only=True)
        j = wait(self.db, jid)
        self.assertEqual(j["status"], "script_ready", j.get("error"))
        self.assertTrue(pathlib.Path(j["script_path"]).exists())
        jid2 = self.jobs.start(self.s, from_job=jid)
        j2 = wait(self.db, jid2)
        self.assertEqual(j2["status"], "done", j2.get("error"))
        v = self.db.get_video(j2["video_id"])
        self.assertEqual(v["category"], "science")
        self.assertEqual(len(v["claims"]), 2)
        self.assertEqual(v["sources"][0]["source"], "Pixabay")
        errs, _ = self.checks.validate_video(v, self.s)
        self.assertTrue(any("사실 확인" in e for e in errs))
        self.db.update_video(v["id"], claims=[{**c, "checked": True} for c in v["claims"]])
        errs, _ = self.checks.validate_video(self.db.get_video(v["id"]), self.s)
        self.assertFalse(any("사실 확인" in e for e in errs))

    def test_guards(self):
        with self.assertRaises(self.jobs.JobError):
            self.jobs.start(self.s, "x", "science", "humor")
        with self.assertRaises(self.jobs.JobError):
            self.jobs.start(self.s, "   ", "science", "science")

    def test_failure_and_lock_release(self):
        (self.pd / "main.py").write_text("import sys; print('boom'); sys.exit(3)", encoding="utf-8")
        j = wait(self.db, self.jobs.start(self.s, "a", "science", "science", True))
        self.assertEqual(j["status"], "failed")
        j2 = wait(self.db, self.jobs.start(self.s, "b", "science", "science", True))   # 락이 풀려 다시 시작 가능
        self.assertEqual(j2["status"], "failed")

    def test_migration_from_old_db(self):
        old = self.home / "old"
        old.mkdir()
        import os
        os.environ["YT_PUBLISHER_HOME"] = str(old)
        from yt_publisher import config
        importlib.reload(config)
        old.mkdir(exist_ok=True)
        c = sqlite3.connect(str(old / "publisher.db"))
        c.executescript("CREATE TABLE videos (id INTEGER PRIMARY KEY, format TEXT NOT NULL, category TEXT, title TEXT NOT NULL, description TEXT DEFAULT '', tags TEXT DEFAULT '[]', file_path TEXT NOT NULL, file_hash TEXT, channel_id TEXT DEFAULT 'default', status TEXT NOT NULL DEFAULT 'draft', publish_at TEXT, youtube_id TEXT, affiliate INTEGER DEFAULT 0, rights_confirmed INTEGER DEFAULT 0, synthetic INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0, next_attempt_at TEXT, error TEXT, created_at TEXT, updated_at TEXT, uploaded_at TEXT); INSERT INTO videos(format,title,file_path) VALUES('shorts','옛영상','/x.mp4');")
        c.commit(); c.close()
        importlib.reload(self.db)
        self.db.init()
        v = self.db.list_videos()[0]
        self.assertEqual(v["claims"], [])


if __name__ == "__main__":
    unittest.main()
