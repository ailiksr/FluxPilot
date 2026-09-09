import unittest
from unittest.mock import patch

from core import storage


class TestStorageReads(unittest.TestCase):
    def test_actions_use_jsonl_in_jsonl_mode(self):
        fallback = [{"action": "article_archive_approved", "advice": {"entry_id": 7}}]
        with patch.object(storage, "MODE", "jsonl"), patch.object(
            storage, "_query_raw", side_effect=AssertionError("unexpected database read")
        ):
            self.assertEqual(storage.read_actions(lambda: fallback), fallback)

    def test_actions_use_postgres_in_postgres_mode(self):
        fallback = [{"action": "jsonl"}]
        postgres = [{"action": "postgres"}]
        with patch.object(storage, "MODE", "postgres"), patch.object(
            storage, "_query_raw", return_value=postgres
        ):
            self.assertEqual(storage.read_actions(lambda: fallback), postgres)

    def test_actions_fall_back_when_postgres_read_fails(self):
        fallback = [{"action": "article_archive_rollback", "advice": {"entry_id": 7}}]
        with patch.object(storage, "MODE", "postgres"), patch.object(
            storage, "_query_raw", side_effect=RuntimeError("database unavailable")
        ):
            self.assertEqual(storage.read_actions(lambda: fallback), fallback)


if __name__ == "__main__":
    unittest.main()
