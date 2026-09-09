import unittest
from unittest.mock import patch, MagicMock
from flask import Flask

from app.routes.scoring import scoring_bp


class TestReEvaluateEndpoint(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(scoring_bp)
        self.client = self.app.test_client()

    @patch("core.miniflux_client.get_miniflux_client")
    @patch("app.routes._shared.read_scoring_rows")
    @patch("app.routes._shared.read_actions", return_value=[])
    @patch("app.routes._shared.read_benchmark_reviews", return_value={})
    @patch("app.routes._shared.read_taxonomy_feedback", return_value={})
    def test_benchmark_detail_includes_trace_and_rules(self, mock_tax, mock_rev, mock_act, mock_rows, mock_client):
        mock_client.return_value.get_entry.return_value = {"url": "https://example.com/test"}
        mock_rows.return_value = [{
            "entry_id": 999,
            "title": "大模型智能体技术演进",
            "score": 85,
            "judge": {"taxonomy": {"topics": ["技术"], "matched_keywords": ["AI"]}},
            "pipeline_trace": {"stage": "llm_judged", "base_score": 85}
        }]
        resp = self.client.get("/api/benchmark/999/detail")
        self.assertEqual(resp.status_code, 200)
        d = resp.get_json()
        self.assertEqual(d["entry_id"], 999)
        self.assertIn("pipeline_trace", d)
        self.assertIn("rule_match", d)
        self.assertEqual(d["pipeline_trace"]["stage"], "llm_judged")

    @patch("core.miniflux_client.get_miniflux_client")
    @patch("app.routes._shared.read_scoring_rows")
    @patch("core.auto_actions.auto_star_entry")
    def test_re_evaluate_endpoint_updates_score(self, mock_auto_star, mock_rows, mock_client):
        mock_client.return_value.get_entry.return_value = {"url": "https://example.com/test"}
        mock_rows.return_value = [{
            "entry_id": 888,
            "title": "前沿架构突破",
            "score": 70,
            "judge": {"taxonomy": {"topics": ["技术"], "matched_keywords": ["架构"]}},
        }]
        with patch("core.rules_store.load_rules", return_value={"boost_keywords": ["架构"], "boost_topics": [], "mute_keywords": [], "mute_topics": [], "mute_content_types": []}):
            resp = self.client.post("/api/benchmark/888/re-evaluate")
            self.assertEqual(resp.status_code, 200)
            d = resp.get_json()
            self.assertEqual(d["entry_id"], 888)
            # Boosted +15: 70 + 15 = 85
            self.assertEqual(d["updated_score"], 85)
            self.assertTrue(d["rule_match"]["boosted"])


if __name__ == "__main__":
    unittest.main()
