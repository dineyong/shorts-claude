import unittest
from tests.helpers import fresh_home, make_video


class W1(unittest.TestCase):
    def setUp(self):
        self.home = fresh_home()
        from yt_publisher import db, settings
        self.db, self.settings = db, settings

    def test_dirs_and_defaults(self):
        from yt_publisher import config
        for cat in ("drama_movie", "shopping", "humor", "science"):
            self.assertTrue((config.INBOX_DIR / "shorts" / cat).is_dir())
        self.assertTrue((config.INBOX_DIR / "longform").is_dir())
        s = self.db.get_settings()
        self.assertFalse(s["longform"]["enabled"])
        self.assertEqual(s["mode"], "demo")
        self.assertEqual(self.db.list_channels()[0]["id"], "default")

    def test_settings_merge_persist(self):
        self.db.save_settings({"shorts": {"slots": ["10:00"]}, "mode": "live"})
        s = self.db.get_settings()
        self.assertEqual(s["shorts"]["slots"], ["10:00"])
        self.assertTrue(s["shorts"]["add_shorts_tag"])      # 나머지는 기본값 유지
        self.assertEqual(s["mode"], "live")

    def test_video_crud_and_hash_unique(self):
        f = make_video(self.home)
        vid = self.db.add_video(format="shorts", category="science", title="t", file_path=f, file_hash="h1", tags=["a", "b"])
        v = self.db.get_video(vid)
        self.assertEqual(v["tags"], ["a", "b"])
        self.assertEqual(v["status"], "draft")
        self.assertEqual(self.db.find_by_hash("h1")["id"], vid)
        with self.assertRaises(Exception):
            self.db.add_video(format="shorts", category="science", title="t2", file_path=f, file_hash="h1")
        self.db.update_video(vid, status="queued", tags=["x"])
        self.assertEqual(self.db.get_video(vid)["tags"], ["x"])
        with self.assertRaises(ValueError):
            self.db.update_video(vid, bogus=1)
        self.assertEqual(len(self.db.list_videos(fmt="shorts", category="science")), 1)
        self.assertEqual(len(self.db.list_videos(fmt="longform")), 0)
        self.db.delete_video(vid)
        self.assertIsNone(self.db.get_video(vid))

    def test_checks_rules(self):
        from yt_publisher.checks import validate_video
        s = self.db.get_settings()
        f = make_video(self.home)
        base = dict(format="shorts", category="science", title="제목", description="", tags=[], file_path=f)
        self.assertEqual(validate_video(base, s)[0], [])
        # 롱폼 비활성
        e, _ = validate_video({**base, "format": "longform", "category": None}, s)
        self.assertTrue(any("롱폼" in x for x in e))
        # 드라마/영화는 사용권 확인 필수
        e, _ = validate_video({**base, "category": "drama_movie"}, s)
        self.assertTrue(any("사용권" in x for x in e))
        e, _ = validate_video({**base, "category": "drama_movie", "rights_confirmed": 1}, s)
        self.assertEqual(e, [])
        # 쇼핑 제휴는 대가 표시 필수
        e, _ = validate_video({**base, "category": "shopping", "affiliate": 1, "description": "링크 있음"}, s)
        self.assertTrue(any("대가 표시" in x for x in e))
        e, _ = validate_video({**base, "category": "shopping", "affiliate": 1, "description": "제휴 링크이며 수수료를 받을 수 있습니다"}, s)
        self.assertEqual(e, [])
        # 제목/파일
        e, _ = validate_video({**base, "title": "가" * 101}, s)
        self.assertTrue(any("100자" in x for x in e))
        e, _ = validate_video({**base, "file_path": "/nope.mp4"}, s)
        self.assertTrue(any("찾을 수 없" in x for x in e))
        e, _ = validate_video({**base, "category": "nope"}, s)
        self.assertTrue(any("카테고리" in x for x in e))


if __name__ == "__main__":
    unittest.main()
