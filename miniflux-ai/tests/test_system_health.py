import unittest
from unittest.mock import patch

from core import system_health
from common import config as common_config


class TestSystemHealth(unittest.TestCase):
    def test_llm_not_configured(self):
        with patch.object(common_config, "llm_base_url", ""), \
             patch.object(common_config, "llm_api_key", ""):
            result = system_health.check_llm()
        self.assertFalse(result["ok"])
        self.assertIn("not_configured", result["detail"])

    def test_llm_ok_with_recent_scores(self):
        rows = [{"entry_id": 1, "score": 70, "scored_at": "2026-08-30T10:00:00+00:00"}]
        with patch.object(common_config, "llm_base_url", "http://llm:8080/v1"), \
             patch.object(common_config, "llm_api_key", "sk-test"), \
             patch("app.routes._shared.read_scoring_rows", return_value=rows):
            result = system_health.check_llm()
        self.assertTrue(result["ok"])
        self.assertIn("last_scored_at", result)

    def test_summary_empty_when_no_file(self):
        with patch("core.system_health._data_dir", return_value=system_health.Path("/nonexistent")):
            result = system_health.check_summary()
        self.assertEqual(result["summary_entries"], 0)
        self.assertFalse(result["summary_exists"])

    def test_summary_counts_entries(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = system_health.Path(tmp) / "summary.dat"
            p.write_text('{"id":1}\n{"id":2}\n', encoding="utf-8")
            with patch("core.system_health._data_dir", return_value=system_health.Path(tmp)):
                result = system_health.check_summary()
            self.assertEqual(result["summary_entries"], 2)
            self.assertTrue(result["summary_exists"])

    def test_report_has_all_sections(self):
        with patch.object(system_health, "check_llm", return_value={"ok": True}), \
             patch.object(system_health, "check_storage", return_value={"storage": {"postgres_reachable": True}, "writes": {}}), \
             patch.object(system_health, "check_summary", return_value={"summary_entries": 0}), \
             patch.object(system_health, "check_outbox", return_value={"pending": 0}), \
             patch.object(system_health, "check_backup", return_value={"available": True, "last_backup": "x"}):
            r = system_health.report()
        self.assertTrue(r["ok"])
        self.assertTrue(r["production_unchanged"])
        for key in ("llm", "storage", "summary", "outbox", "backup"):
            self.assertIn(key, r)

    def test_backup_no_file(self):
        with patch("core.system_health._data_dir", return_value=system_health.Path("/nonexistent")):
            r = system_health.check_backup()
        self.assertFalse(r["available"])

    def test_backup_reads_status(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = system_health.Path(tmp) / "backup_status.json"
            p.write_text('{"last_backup":"20260830T005400Z","files":11,"ok":true}', encoding="utf-8")
            with patch("core.system_health._data_dir", return_value=system_health.Path(tmp)):
                r = system_health.check_backup()
            self.assertTrue(r["available"])
            self.assertEqual(r["last_backup"], "20260830T005400Z")
            self.assertEqual(r["files"], 11)


if __name__ == "__main__":
    unittest.main()

    def test_llm_no_scoring_data(self):
        with patch.object(common_config, "llm_base_url", "http://llm:8080/v1"), \
             patch.object(common_config, "llm_api_key", "sk-test"), \
             patch("app.routes._shared.read_scoring_rows", return_value=[]):
            result = system_health.check_llm()
        self.assertFalse(result["ok"])
        self.assertIn("no_scoring_data", result["detail"])
