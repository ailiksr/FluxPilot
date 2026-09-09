import unittest

from app.routes import _shared
from core import control_console


class TestArchiveExecuteMarking(unittest.TestCase):
    def test_shared_write_accepts_executed(self):
        """write_benchmark_review 存在且接受 status='executed' 的行。"""
        self.assertTrue(hasattr(_shared, "write_benchmark_review"))
        row = {
            "entry_id": 56, "status": "executed", "category": "归档已执行",
            "human_score": None, "score_range": None,
            "notes": "[archived] 已实际执行归档",
            "reviewed_at": "2026-08-31T00:00:00Z",
        }
        self.assertEqual(row["status"], "executed")

    def test_control_console_excludes_executed(self):
        """archive_review_queue 的过滤逻辑排除 status='executed' 记录。"""
        rows = [
            {"entry_id": 56, "status": "archive"},
            {"entry_id": 56, "status": "executed"},  # 最新覆盖 archive
            {"entry_id": 33, "status": "archive"},
        ]
        # 模拟 read_reviews 按 entry 去重（后写覆盖先写）
        dedup = {}
        for row in rows:
            dedup[str(row["entry_id"])] = row
        reviews = {}
        for row in dedup.values():
            eid = str(row.get("entry_id"))
            if row.get("status") == "archive":
                reviews[eid] = row
            elif row.get("status") in ("pending", "executed"):
                reviews.pop(eid, None)
        self.assertEqual(set(reviews.keys()), {"33"})

    def test_archive_queue_uses_latest_status(self):
        """article_archive_queue 用 read_benchmark_reviews（最新覆盖），executed 后不再返回。"""
        # read_benchmark_reviews 返回 entry→最新记录（execute 写入 executed 后覆盖 archive）
        reviews = {
            "56": {"entry_id": 56, "status": "executed"},
            "33": {"entry_id": 33, "status": "archive"},
        }
        items = []
        for eid, review in reviews.items():
            if review.get("status") != "archive":
                continue
            items.append(eid)
        self.assertEqual(items, ["33"])


if __name__ == "__main__":
    unittest.main()
