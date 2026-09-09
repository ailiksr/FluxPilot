import unittest
from unittest.mock import MagicMock, patch

from core.auto_actions import auto_star_entry, auto_silence_entry, build_score_badge


class TestAutoActions(unittest.TestCase):
    def test_auto_star_entry_not_eligible(self):
        # Score too low and not boosted -> skip
        res = auto_star_entry(101, score=60, is_boosted=False)
        self.assertFalse(res)

    def test_auto_star_entry_already_starred_idempotent(self):
        # Entry already starred -> should not toggle
        mock_client = MagicMock()
        with patch("core.auto_actions.get_miniflux_client", return_value=mock_client):
            res = auto_star_entry(102, score=85, entry_dict={"starred": True})
            self.assertFalse(res)
            mock_client.toggle_bookmark.assert_not_called()

    def test_auto_star_entry_success(self):
        mock_client = MagicMock()
        with patch("core.auto_actions.get_miniflux_client", return_value=mock_client):
            res = auto_star_entry(103, score=88, entry_dict={"starred": False})
            self.assertTrue(res)
            mock_client.toggle_bookmark.assert_called_once_with(103)

    def test_auto_silence_entry_not_eligible(self):
        # Regular score without mute -> skip
        res = auto_silence_entry(201, score=50, is_muted=False)
        self.assertFalse(res)

    def test_auto_silence_entry_already_read_idempotent(self):
        mock_client = MagicMock()
        with patch("core.auto_actions.get_miniflux_client", return_value=mock_client):
            res = auto_silence_entry(202, score=15, entry_dict={"status": "read"})
            self.assertFalse(res)
            mock_client.update_entries.assert_not_called()

    def test_auto_silence_entry_success_with_audit(self):
        mock_client = MagicMock()
        recorded = []
        with patch("core.auto_actions.get_miniflux_client", return_value=mock_client), \
             patch("core.advice_store.record", side_effect=lambda act, adv: recorded.append((act, adv))):
            res = auto_silence_entry(203, score=20, is_muted=True, mute_reasons=["命中屏蔽词: 折扣"], entry_dict={"status": "unread", "title": "大减价"})
            self.assertTrue(res)
            mock_client.update_entries.assert_called_once_with([203], "read")
            self.assertEqual(len(recorded), 1)
            self.assertEqual(recorded[0][0], "auto_archive_silenced")
            self.assertEqual(recorded[0][1]["entry_id"], 203)
            self.assertEqual(recorded[0][1]["previous_status"], "unread")

    def test_build_score_badge(self):
        badge = build_score_badge(85)
        self.assertIn("85/100", badge)
        self.assertIn("优先精选", badge)

        badge_low = build_score_badge(20)
        self.assertIn("20/100", badge_low)
        self.assertIn("垃圾水文", badge_low)

    def test_build_decision_inspector(self):
        from core.auto_actions import build_decision_inspector
        scoring = {
            "score": 85,
            "reason": "强项：信息增量、内容深度",
            "judge": {
                "information": 5, "depth": 4, "evidence": 4, "promotional": 0,
                "taxonomy": {"topics": ["技术"], "matched_keywords": ["架构", "分布式"]}
            },
            "pipeline_trace": {"stage": "llm_judged"}
        }
        rule_match = {"boosted": True}
        html = build_decision_inspector(scoring, rule_match, entry_id=123)
        self.assertIn("<details", html)
        self.assertIn("85/100", html)
        self.assertIn("优先精选", html)
        self.assertIn("研判路径", html)
        self.assertIn("规则加权提权", html)
        self.assertIn("架构", html)
        self.assertIn("规则快捷管理", html)


if __name__ == "__main__":
    unittest.main()
