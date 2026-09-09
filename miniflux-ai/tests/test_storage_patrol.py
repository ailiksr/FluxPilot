import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.storage_patrol import run_storage_sync


class TestStoragePatrol(unittest.TestCase):
    @patch("core.storage_patrol._read_jsonl")
    @patch("core.export_outbox.main", return_value=5)
    @patch("psycopg.connect")
    def test_run_storage_sync(self, mock_connect, mock_drain, mock_read_jsonl):
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.side_effect = [
            (100,),  # scoring_results
            (50,),   # review_events
            (2,),    # taxonomy_feedback
            (10,),   # action_events
        ]

        # Mock JSONL files
        mock_read_jsonl.side_effect = [
            ([{"entry_id": i} for i in range(100)], 0),
            ([{"entry_id": i} for i in range(50)], 0),
            ([{"entry_id": i} for i in range(2)], 0),
            ([{"id": i} for i in range(10)], 0),
        ]

        with patch("core.storage_patrol.REPORT_FILE", Path("/tmp/test_control_consistency.json")):
            report = run_storage_sync()
            self.assertEqual(report["version"], "control-consistency-v1")
            self.assertTrue(report["ok"])
            self.assertEqual(report["container_patrol"], True)
            self.assertEqual(report["exported_events"], 5)


if __name__ == "__main__":
    unittest.main()
