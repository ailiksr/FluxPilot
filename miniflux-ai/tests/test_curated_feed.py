import unittest
from unittest.mock import patch

from core import curated_feed


class TestCuratedFeed(unittest.TestCase):
    def _row(self, eid, score, title=None, link="http://example.com/x"):
        return {
            "entry_id": eid,
            "score": score,
            "title": title or f"文章{eid}",
            "url": link,
            "reason": "信息增量高",
            "scored_at": "2026-08-30T10:00:00+00:00",
        }

    def _gen(self, rows, min_score=70, limit=30):
        with patch("app.routes._shared.read_scoring_rows", return_value=rows):
            return curated_feed.generate_curated_rss(min_score=min_score, limit=limit)

    def test_generate_returns_rss_xml(self):
        xml = self._gen([self._row(1, 85), self._row(2, 72), self._row(3, 40)], min_score=70)
        self.assertIn("<rss", xml)
        self.assertIn("<channel>", xml)
        self.assertEqual(xml.count("<item>"), 2)

    def test_min_score_filter(self):
        xml = self._gen([self._row(1, 90), self._row(2, 60), self._row(3, 30)], min_score=80)
        self.assertEqual(xml.count("<item>"), 1)

    def test_limit(self):
        rows = [self._row(i, 90 - i) for i in range(1, 11)]
        xml = self._gen(rows, min_score=0, limit=3)
        self.assertEqual(xml.count("<item>"), 3)

    def test_score_sort_descending(self):
        rows = [self._row(1, 70), self._row(2, 95), self._row(3, 80)]
        xml = self._gen(rows, min_score=0, limit=10)
        positions = [xml.index(f"文章{i}") for i in (2, 3, 1)]
        self.assertEqual(positions, sorted(positions))

    def test_dedupe_by_entry_id(self):
        rows = [self._row(1, 70), self._row(1, 90)]
        xml = self._gen(rows, min_score=0)
        self.assertEqual(xml.count("<item>"), 1)

    def test_invalid_scores_excluded(self):
        rows = [
            {"entry_id": 1, "score": "not-a-number", "title": "bad"},
            self._row(2, 75),
        ]
        xml = self._gen(rows, min_score=0)
        self.assertEqual(xml.count("<item>"), 1)


if __name__ == "__main__":
    unittest.main()
