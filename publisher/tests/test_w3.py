import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from tests.helpers import fresh_home, make_video

KST = ZoneInfo("Asia/Seoul")
T0 = dt.datetime(2026, 10, 15, 11, 0, tzinfo=KST)


class W3(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        import importlib
        from yt_publisher import db, publisher, stats, worker, mock
        importlib.reload(mock)
        self.db, self.pub, self.stats, self.worker, self.mock = db, publisher, stats, worker, mock
        self.n = 0
        self.client = mock.MockClient()
        self.cf = lambda ch, s: self.client

    def vid(self, cat="science"):
        self.n += 1
        f = make_video(self.home, f"v{self.n}.mp4", f"d{self.n}".encode())
        return self.db.add_video(format="shorts", category=cat, title=f"영상{self.n}", file_path=f, file_hash=f"h{self.n}")

    def publish(self, vid, at=T0):
        self.pub.enqueue(vid, now=at)
        self.pub.process_queue(self.cf, now=at)

    def test_end_to_end_with_worker(self):
        a, b = self.vid("science"), self.vid("humor")
        self.db.save_settings({"auto_queue": ["science", "humor"]})
        r = self.worker.run_once(self.cf, now=T0)
        self.assertEqual(sorted(r["auto_queued"]), sorted([a, b]))
        self.assertEqual(sorted(r["publish"]["uploaded"]), sorted([a, b]))
        self.assertEqual(r["stats"]["sampled"], [])                 # 아직 공개 전
        # 다음 날: 공개 확인 + 첫 통계
        t1 = T0 + dt.timedelta(days=1)
        self.client.now = t1
        r = self.worker.run_once(self.cf, now=t1)
        self.assertEqual(sorted(r["sync"]["published"]), sorted([a, b]))
        self.assertEqual(sorted(r["stats"]["sampled"]), sorted([a, b]))
        self.assertIsNotNone(self.worker.last_tick())

    def test_collect_interval_policy(self):
        v = self.vid()
        self.publish(v)
        pub_at = dt.datetime.fromisoformat(self.db.get_video(v)["publish_at"])
        t = pub_at + dt.timedelta(hours=2)
        self.client.now = t
        self.pub.sync_published(self.cf, now=t)
        self.assertEqual(self.stats.collect(self.cf, now=t)["sampled"], [v])
        self.assertEqual(self.stats.collect(self.cf, now=t + dt.timedelta(minutes=30))["skipped"], 1)
        self.client.now = t + dt.timedelta(minutes=61)
        self.assertEqual(self.stats.collect(self.cf, now=t + dt.timedelta(minutes=61))["sampled"], [v])
        # 2일 넘으면 6시간 간격
        late = pub_at + dt.timedelta(days=3)
        self.client.now = late
        self.assertEqual(self.stats.collect(self.cf, now=late)["sampled"], [v])
        self.assertEqual(self.stats.collect(self.cf, now=late + dt.timedelta(hours=2))["skipped"], 1)
        self.assertEqual(self.stats.interval_for(100, 60), 360)
        self.assertEqual(self.stats.interval_for(1000, 60), 1440)

    def _sample(self, v, hours_list):
        pub_at = dt.datetime.fromisoformat(self.db.get_video(v)["publish_at"])
        self.pub.sync_published(self.cf, now=pub_at + dt.timedelta(hours=hours_list[0]))
        for h in hours_list:
            t = pub_at + dt.timedelta(hours=h)
            self.client.now = t
            self.pub.sync_published(self.cf, now=t)
            self.stats.collect(self.cf, now=t, force=True)
        return pub_at

    def test_summary_and_overview(self):
        a, b = self.vid("science"), self.vid("humor")
        self.publish(a); self.publish(b)
        pa = self._sample(a, [1, 25, 49])
        self._sample(b, [1, 25, 49])
        now = pa + dt.timedelta(hours=50)
        o = self.stats.overview(now)
        self.assertEqual(o["counts"]["published"], 2)
        self.assertEqual(set(o["by_category"]), {"science", "humor"})
        sa = [r for r in o["videos"] if r["id"] == a][0]
        self.assertGreater(sa["views"], 0)
        self.assertGreater(sa["views_24h"], 0)
        self.assertLessEqual(sa["views_24h"], sa["views"])
        self.assertEqual(o["total"]["videos"], 2)
        self.assertEqual(o["total"]["views"], sum(r["views"] for r in o["videos"]))
        self.assertEqual(len(o["top"]), 2)
        # 포맷 필터
        self.assertEqual(self.stats.overview(now, fmt="longform")["total"]["videos"], 0)

    def test_daily_series_sums_to_total(self):
        a = self.vid("science")
        self.publish(a)
        pa = self._sample(a, [1, 20, 30, 50, 80])
        end = pa + dt.timedelta(hours=81)
        series = self.stats.daily_series(days=6, now=end)
        total = sum(d["views"] for d in series)
        last = self.db.snapshots(a)[-1]["views"]
        self.assertEqual(total, last)               # 일별 증가분의 합 = 최신 누적(공개 직후 수집 시작)
        self.assertTrue(all(d["views"] >= 0 for d in series))
        self.assertEqual(self.stats.daily_series(days=6, now=end, category="humor")[-1]["views"], 0)

    def test_missing_video_flagged(self):
        v = self.vid()
        self.publish(v)
        pub_at = dt.datetime.fromisoformat(self.db.get_video(v)["publish_at"])
        self.client.now = pub_at + dt.timedelta(hours=1)
        self.pub.sync_published(self.cf, now=pub_at + dt.timedelta(hours=1))
        import json
        from yt_publisher import config
        config.STATE = None  # noqa (no-op)
        (self.home / "mock_state.json").write_text("{}")             # 유튜브에서 사라진 상황
        r = self.stats.collect(self.cf, now=pub_at + dt.timedelta(hours=2), force=True)
        self.assertEqual(r["missing"], [v])
        self.assertIn("찾을 수 없", self.db.get_video(v)["error"])


if __name__ == "__main__":
    unittest.main()
