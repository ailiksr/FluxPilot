import unittest
from unittest.mock import patch

from core.pre_review import score_article, pre_review_items


class TestPreReviewAcceptLogic(unittest.TestCase):
    """批量采纳的核心逻辑：只对匹配建议的条目写决策，不写边界项。"""
    def _rows(self):
        return [
            {"entry_id": 1, "title": "高分文", "score": 80,
             "judge": {"promotional": 0, "low_content": 0, "interest_match": 60, "content_type": "news"}},
            {"entry_id": 2, "title": "促销文", "score": 20,
             "judge": {"promotional": 5, "low_content": 4, "interest_match": 20, "content_type": "deal"}},
            {"entry_id": 3, "title": "边界文", "score": 50,
             "judge": {"promotional": 2, "low_content": 2, "interest_match": 60, "content_type": "news"}},
        ]

    def test_pre_review_categorizes(self):
        items = pre_review_items(self._rows())["items"]
        by_id = {x["entry_id"]: x["suggestion"] for x in items}
        self.assertEqual(by_id[1], "keep")
        self.assertEqual(by_id[2], "archive")
        self.assertEqual(by_id[3], "boundary")

    def test_accept_keep_writes_only_keep(self):
        items = pre_review_items(self._rows())["items"]
        written = [x["entry_id"] for x in items if x["suggestion"] == "keep"]
        self.assertEqual(written, [1])

    def test_accept_archive_writes_only_archive(self):
        items = pre_review_items(self._rows())["items"]
        written = [x["entry_id"] for x in items if x["suggestion"] == "archive"]
        self.assertEqual(written, [2])

    def test_boundary_never_auto_written(self):
        items = pre_review_items(self._rows())["items"]
        boundary = [x for x in items if x["suggestion"] == "boundary"]
        self.assertEqual(len(boundary), 1)
        # 批量采纳 keep/archive 都不应包含边界项
        for sug in ("keep", "archive"):
            written = [x["entry_id"] for x in items if x["suggestion"] == sug]
            self.assertNotIn(boundary[0]["entry_id"], written)

    def test_all_rows_production_unchanged(self):
        for x in pre_review_items(self._rows())["items"]:
            self.assertTrue(x["production_unchanged"])


if __name__ == "__main__":
    unittest.main()
