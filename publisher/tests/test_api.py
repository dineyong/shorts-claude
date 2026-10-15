import json
import threading
import unittest
import urllib.error
import urllib.request
from tests.helpers import fresh_home, make_video


class Api(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        import importlib
        from yt_publisher import mock, server
        importlib.reload(mock)
        importlib.reload(server)
        self.server = server
        self.srv = server.make_server(0)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()

    def call(self, method, path, body=None, raw=None, headers=None, host=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"X-Requested-With": "yt-publisher", **(headers or {})}
        if host:
            h["Host"] = host
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read().decode() or "null") if r.headers["Content-Type"].startswith("application/json") else r.read()
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    def test_state_and_static(self):
        st, d = self.call("GET", "/api/state")
        self.assertEqual(st, 200)
        self.assertEqual(set(d["shorts_categories"]), {"drama_movie", "shopping", "humor", "science"})
        self.assertFalse(d["settings"]["longform"]["enabled"])
        self.assertEqual(d["settings"]["mode"], "demo")

    def test_security(self):
        st, d = self.call("POST", "/api/inbox/scan", {}, headers={"X-Requested-With": ""})
        self.assertEqual(st, 403)
        st, d = self.call("GET", "/api/state", host="evil.example.com")
        self.assertEqual(st, 403)
        st, d = self.call("GET", "/../../etc/passwd")
        self.assertIn(st, (403, 404))

    def test_upload_edit_queue_flow(self):
        st, d = self.call("POST", "/api/upload?format=shorts&category=drama_movie&name=%EB%93%9C%EB%9D%BC%EB%A7%88.mp4", raw=b"VIDEO1")
        self.assertEqual(st, 200); vid = d["id"]
        st, d = self.call("POST", "/api/upload?format=shorts&category=humor&name=copy.mp4", raw=b"VIDEO1")
        self.assertTrue(d["duplicate"] and d["id"] == vid)
        st, d = self.call("POST", "/api/upload?format=shorts&name=x.mp4", raw=b"X")
        self.assertEqual(st, 400)
        st, d = self.call("POST", "/api/upload?format=shorts&category=humor&name=x.exe", raw=b"X")
        self.assertEqual(st, 400)
        # 드라마/영화는 사용권 확인 없으면 발행 대기 불가
        st, d = self.call("POST", f"/api/videos/{vid}/queue", {})
        self.assertEqual(st, 422); self.assertTrue(any("사용권" in e for e in d["errors"]))
        st, d = self.call("PUT", f"/api/videos/{vid}", {"title": "수정된 제목", "rights_confirmed": True, "tags": "a, #b"})
        self.assertEqual((st, d["title"], d["tags"]), (200, "수정된 제목", ["a", "b"]))
        st, d = self.call("POST", f"/api/videos/{vid}/queue", {})
        self.assertEqual(st, 200); self.assertEqual(d["video"]["status"], "queued")
        st, d = self.call("GET", "/api/schedule?days=3")
        placed = [v for day in d["days"] for c in day["cells"].values() for v in c["videos"]]
        self.assertTrue(any(p["id"] == vid for p in placed) or any(p["id"] == vid for p in d["custom"]))
        # 즉시 실행 → 업로드됨(모의) → 수정/삭제 불가
        st, d = self.call("POST", "/api/run", {})
        self.assertEqual(d["publish"]["uploaded"], [vid])
        st, d = self.call("PUT", f"/api/videos/{vid}", {"title": "x"})
        self.assertEqual(st, 409)
        st, d = self.call("DELETE", f"/api/videos/{vid}")
        self.assertEqual(st, 409)

    def test_longform_gate_and_settings(self):
        st, d = self.call("POST", "/api/upload?format=longform&name=long.mp4", raw=b"LONG")
        vid = d["id"]
        st, d = self.call("POST", f"/api/videos/{vid}/queue", {})
        self.assertEqual(st, 422); self.assertTrue(any("롱폼" in e for e in d["errors"]))
        st, d = self.call("PUT", "/api/settings", {"longform": {"enabled": True}})
        self.assertTrue(d["longform"]["enabled"])
        st, d = self.call("POST", f"/api/videos/{vid}/queue", {})
        self.assertEqual(st, 200)

    def test_inbox_stats_channels_secret(self):
        from yt_publisher import config
        (config.INBOX_DIR / "shorts" / "science" / "s1.mp4").write_bytes(b"S1")
        (config.INBOX_DIR / "shorts" / "science" / "s1.json").write_text(json.dumps({"title": "과학 영상"}), encoding="utf-8")
        st, d = self.call("POST", "/api/inbox/scan", {})
        self.assertEqual(len(d["added"]), 1)
        st, d = self.call("GET", "/api/stats/overview")
        self.assertEqual(st, 200); self.assertEqual(d["total"]["videos"], 0)
        st, d = self.call("GET", "/api/stats/series?days=7")
        self.assertEqual(len(d), 7)
        st, d = self.call("POST", "/api/channels", {"id": "Sci Channel!", "name": "과학 채널"})
        self.assertEqual(d["id"], "scichannel")
        st, d = self.call("POST", "/api/client-secret", raw=b"not json")
        self.assertEqual(st, 400)
        st, d = self.call("POST", "/api/client-secret", raw=json.dumps({"installed": {"client_id": "x"}}).encode())
        self.assertEqual(st, 200)
        st, d = self.call("POST", "/api/channels/default/auth", {})
        self.assertEqual(st, 409)                  # 데모 모드
        st, d = self.call("GET", "/api/logs")
        self.assertEqual(st, 200)


if __name__ == "__main__":
    unittest.main()
