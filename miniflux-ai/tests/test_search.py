import unittest
from unittest.mock import patch

from core import search


class TestSearch(unittest.TestCase):
    def test_empty_query_returns_empty(self):
        with patch("core.search.get_miniflux_client") as mock_client:
            result = search.search_entries("  ")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["items"], [])
        mock_client.assert_not_called()

    def test_search_merges_ai_scores(self):
        entries = [
            {"id": 10, "title": "AI 小甜甜", "url": "http://x/10", "feed_id": 2,
             "status": "unread", "published_at": "2026-08-30T00:00:00Z"},
        ]
        scoring_rows = [
            {"entry_id": 10, "score": 72, "reason": "信息增量高",
             "scored_at": "2026-08-30T01:00:00Z", "title": "AI 小甜甜"},
        ]
        mock_client = unittest.mock.Mock()
        mock_client.get_entries.return_value = {"entries": entries}
        with patch("core.search.get_miniflux_client", return_value=mock_client), \
             patch("app.routes._shared.read_scoring_rows", return_value=scoring_rows):
            result = search.search_entries("AI")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["ai_score"], 72)
        self.assertEqual(result["items"][0]["source"], "miniflux")
        self.assertTrue(result["production_unchanged"])

    def test_local_title_match_for_chinese(self):
        # Miniflux 返回 0 条（中文分词弱），但本地评分标题有匹配
        scoring_rows = [
            {"entry_id": 79, "score": 87, "reason": "高质量",
             "scored_at": "2026-08-30T02:00:00Z", "title": "宝马开始全国一口价"},
        ]
        mock_client = unittest.mock.Mock()
        mock_client.get_entries.return_value = {"entries": []}
        with patch("core.search.get_miniflux_client", return_value=mock_client), \
             patch("app.routes._shared.read_scoring_rows", return_value=scoring_rows):
            result = search.search_entries("宝马")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["entry_id"], 79)
        self.assertEqual(result["items"][0]["source"], "local")

    def test_miniflux_error_returns_local_only(self):
        scoring_rows = [
            {"entry_id": 79, "score": 87, "title": "宝马新闻"},
        ]
        mock_client = unittest.mock.Mock()
        mock_client.get_entries.side_effect = RuntimeError("miniflux down")
        with patch("core.search.get_miniflux_client", return_value=mock_client), \
             patch("app.routes._shared.read_scoring_rows", return_value=scoring_rows):
            result = search.search_entries("宝马")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["source"], "local")

    def test_limit_clamped(self):
        mock_client = unittest.mock.Mock()
        mock_client.get_entries.return_value = {"entries": []}
        with patch("core.search.get_miniflux_client", return_value=mock_client):
            search.search_entries("AI", limit=500)
        args, kwargs = mock_client.get_entries.call_args
        self.assertLessEqual(kwargs.get("limit", 20), 50)


if __name__ == "__main__":
    unittest.main()
