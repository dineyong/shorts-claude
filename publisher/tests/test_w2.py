import datetime as dt
import json
import unittest
from zoneinfo import ZoneInfo
from tests.helpers import fresh_home, make_video

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime(2026, 10, 15, 11, 0, tzinfo=KST)


class W2(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        import importlib
        from yt_publisher import db, publisher, inbox, mock, body
        importlib.reload(mock)
        self.db, self.pub, self.inbox, self.mock, self.body = db, publisher, inbox, mock, body
        self.n = 0

    def vid(self, cat="science", **kw):
        self.n += 1
        f = make_video(self.home, f"v{self.n}.mp4", f"data{self.n}".encode())
        base = dict(format="shorts", category=cat, title=f"t{self.n}", file_path=f, file_hash=f"h{self.n}")
        base.update(kw)
        return self.db.add_video(**base)

    def factory(self, client):
        return lambda ch, s: client

    # ---- 예약 슬롯 ----
    def test_slots_fill_in_order_without_collision(self):
        ids = [self.vid() for _ in range(5)]
        ats = [self.pub.enqueue(i, now=NOW)["publish_at"] for i in ids]
        self.assertEqual(ats[:4], ["2026-10-15T12:30:00+09:00", "2026-10-15T18:30:00+09:00",
                                   "2026-10-15T21:00:00+09:00", "2026-10-16T08:30:00+09:00"])
        self.assertEqual(len(set(ats)), 5)

    def test_enqueue_blocks_invalid(self):
        v = self.vid("drama_movie")
        with self.assertRaises(self.pub.ValidationError):
            self.pub.enqueue(v, now=NOW)
        self.db.update_video(v, rights_confirmed=1)
        self.pub.enqueue(v, now=NOW)
        # 직접 지정한 시각이 너무 가까우면 거부
        w = self.vid()
        with self.assertRaises(self.pub.ValidationError):
            self.pub.enqueue(w, publish_at="2026-10-15T11:10:00+09:00", now=NOW)
        # UTC 로 줘도 같은 시각이면 충돌 없이 한국시간으로 통일
        r = self.pub.enqueue(w, publish_at="2026-10-15T10:00:00+00:00", now=NOW)
        self.assertEqual(r["publish_at"], "2026-10-15T19:00:00+09:00")

    def test_longform_disabled_then_enabled(self):
        f = make_video(self.home, "long.mp4", b"long")
        v = self.db.add_video(format="longform", category=None, title="롱폼", file_path=f, file_hash="L")
        with self.assertRaises(self.pub.ValidationError):
            self.pub.enqueue(v, now=NOW)
        self.db.save_settings({"longform": {"enabled": True}})
        self.assertEqual(self.pub.enqueue(v, now=NOW)["publish_at"], "2026-10-15T19:00:00+09:00")

    # ---- 업로드 ----
    def test_process_upload_and_publish_sync(self):
        v = self.vid()
        self.pub.enqueue(v, now=NOW)
        c = self.mock.MockClient()
        r = self.pub.process_queue(self.factory(c), now=NOW)
        self.assertEqual(r["uploaded"], [v])
        row = self.db.get_video(v)
        self.assertEqual(row["status"], "uploaded")
        self.assertTrue(row["youtube_id"].startswith("MOCK"))
        # 공개 시각 전에는 그대로, 후에는 published
        c.now = NOW
        self.assertEqual(self.pub.sync_published(self.factory(c), now=NOW)["published"], [])
        later = NOW + dt.timedelta(hours=3)
        c.now = later
        self.assertEqual(self.pub.sync_published(self.factory(c), now=later)["published"], [v])
        self.assertEqual(self.db.get_video(v)["status"], "published")

    def test_retry_backoff_then_success(self):
        v = self.vid()
        self.pub.enqueue(v, now=NOW)
        c = self.mock.MockClient(fail_next=1)
        r = self.pub.process_queue(self.factory(c), now=NOW)
        self.assertEqual(r["deferred"], [v])
        row = self.db.get_video(v)
        self.assertEqual((row["status"], row["attempts"]), ("queued", 1))
        # 재시도 시각 전에는 건너뜀
        self.assertEqual(self.pub.process_queue(self.factory(c), now=NOW)["deferred"], [v])
        r = self.pub.process_queue(self.factory(c), now=NOW + dt.timedelta(minutes=2))
        self.assertEqual(r["uploaded"], [v])

    def test_fails_after_max_attempts(self):
        v = self.vid()
        self.pub.enqueue(v, now=NOW)
        c = self.mock.MockClient(fail_next=99)
        t = NOW
        for _ in range(self.pub.MAX_ATTEMPTS):
            self.pub.process_queue(self.factory(c), now=t)
            t += dt.timedelta(hours=1)
        self.assertEqual(self.db.get_video(v)["status"], "failed")
        self.pub.unqueue(v)
        self.assertEqual(self.db.get_video(v)["status"], "draft")

    def test_not_authorized_does_not_burn_attempts(self):
        v = self.vid()
        self.pub.enqueue(v, now=NOW)
        c = self.mock.MockClient(authorized=False)
        self.pub.process_queue(self.factory(c), now=NOW)
        row = self.db.get_video(v)
        self.assertEqual((row["status"], row["attempts"]), ("queued", 0))
        self.assertIn("로그인", row["error"])

    def test_daily_cap_and_expired_slot_reslot(self):
        self.db.save_settings({"daily_upload_cap": 1})
        a, b = self.vid(), self.vid()
        self.pub.enqueue(a, now=NOW); self.pub.enqueue(b, now=NOW)
        c = self.mock.MockClient()
        r = self.pub.process_queue(self.factory(c), now=NOW)
        self.assertEqual((r["uploaded"], r["deferred"]), ([a], [b]))
        # 다음 날 처리하는데 예약 시각(10/15 18:30)이 이미 지났으면 새 슬롯으로 이동
        r = self.pub.process_queue(self.factory(c), now=NOW + dt.timedelta(days=1))
        self.assertEqual(r["uploaded"], [b])
        self.assertGreater(self.db.get_video(b)["publish_at"], "2026-10-16T12:00")

    # ---- 본문 ----
    def test_body_rules(self):
        s = self.db.get_settings()
        v = dict(format="shorts", category="shopping", title="<b>제목</b>", description="설명 <x>", tags=["#a", "b,c"],
                 publish_at="2026-10-16T12:30:00+09:00", affiliate=1, synthetic=0)
        body, part = self.body.build(v, s)
        self.assertNotIn("<", body["snippet"]["title"] + body["snippet"]["description"])
        self.assertTrue(body["snippet"]["description"].endswith("#Shorts"))
        self.assertEqual(body["snippet"]["categoryId"], "22")
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], v["publish_at"])
        self.assertTrue(body["paidProductPlacementDetails"]["hasPaidProductPlacement"])
        self.assertIn("paidProductPlacementDetails", part)
        v2 = {**v, "category": "science", "affiliate": 0}
        b2, p2 = self.body.build(v2, s)
        self.assertNotIn("paidProductPlacementDetails", b2)
        self.assertEqual(p2, "snippet,status")
        self.assertEqual(b2["snippet"]["categoryId"], "28")
        # 롱폼 템플릿/기본 태그
        s["longform"].update(description_template="{description}\n\n구독 부탁드려요", default_tags=["롱폼"])
        b3, _ = self.body.build({**v2, "format": "longform", "category": None}, s)
        self.assertIn("구독 부탁드려요", b3["snippet"]["description"])
        self.assertNotIn("#Shorts", b3["snippet"]["description"])
        self.assertIn("롱폼", b3["snippet"]["tags"])

    # ---- 폴더 읽어오기 ----
    def test_inbox_scan_and_dedupe(self):
        from yt_publisher import config
        d = config.INBOX_DIR / "shorts" / "humor"
        (d / "a.mp4").write_bytes(b"AAA")
        (d / "a.json").write_text(json.dumps({"title": "웃긴 영상", "tags": ["웃김"], "description": "d"}), encoding="utf-8")
        (d / "b.mp4").write_bytes(b"BBB")
        (config.INBOX_DIR / "longform" / "L.mp4").write_bytes(b"LLL")
        (d / "note.txt").write_text("x")
        r = self.inbox.scan_inbox()
        self.assertEqual(len(r["added"]), 3)
        vs = {v["title"]: v for v in self.db.list_videos()}
        self.assertEqual(vs["웃긴 영상"]["category"], "humor")
        self.assertEqual(vs["웃긴 영상"]["tags"], ["웃김"])
        self.assertEqual(vs["b"]["status"], "draft")
        self.assertEqual(vs["L"]["format"], "longform")
        # 이름만 바꿔 복사해도 중복
        (d / "copy_of_b.mp4").write_bytes(b"BBB")
        r2 = self.inbox.scan_inbox()
        self.assertEqual(r2["added"], [])
        self.assertEqual(r2["skipped"], 4)


if __name__ == "__main__":
    unittest.main()
