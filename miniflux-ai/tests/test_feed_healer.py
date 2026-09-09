import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.feed_healer import heal_feed, heal_all_feeds, CHROME_DESKTOP_UA


class TestFeedHealer(unittest.TestCase):
    def test_heal_feed_healthy_skips(self):
        feed = {"id": 1, "title": "Healthy Feed", "parsing_error_count": 0, "disabled": False, "parsing_error_message": ""}
        res = heal_feed(feed)
        self.assertEqual(res["status"], "healthy")

    def test_heal_feed_timeout_disables_http2(self):
        feed = {
            "id": 2,
            "title": "Bohaishibei",
            "parsing_error_count": 3,
            "parsing_error_message": 'Get "https://example.com/feed": context deadline exceeded while awaiting headers',
            "disabled": False,
            "disable_http2": False,
        }
        mock_client = MagicMock()
        with patch("core.feed_healer.get_miniflux_client", return_value=mock_client), \
             patch("core.feed_healer._record_heal") as mock_record:
            res = heal_feed(feed, recent_logs=[])
            self.assertEqual(res["status"], "healed")
            self.assertTrue(res["updates"]["disable_http2"])
            mock_client.update_feed.assert_called_once_with(2, disable_http2=True)
            mock_client.refresh_feed.assert_called_once_with(2)

    def test_heal_feed_403_injects_chrome_ua(self):
        feed = {
            "id": 3,
            "title": "Protected Feed",
            "parsing_error_count": 2,
            "parsing_error_message": "HTTP 403 Forbidden Cloudflare block",
            "disabled": False,
            "user_agent": "Miniflux/2.0",
        }
        mock_client = MagicMock()
        with patch("core.feed_healer.get_miniflux_client", return_value=mock_client), \
             patch("core.feed_healer._record_heal"):
            res = heal_feed(feed, recent_logs=[])
            self.assertEqual(res["status"], "healed")
            self.assertEqual(res["updates"]["user_agent"], CHROME_DESKTOP_UA)
            mock_client.update_feed.assert_called_once_with(3, user_agent=CHROME_DESKTOP_UA)

    def test_heal_feed_disabled_reactivates(self):
        feed = {
            "id": 4,
            "title": "Suspended Feed",
            "parsing_error_count": 5,
            "parsing_error_message": "temporary connection failure",
            "disabled": True,
        }
        mock_client = MagicMock()
        with patch("core.feed_healer.get_miniflux_client", return_value=mock_client), \
             patch("core.feed_healer._record_heal"):
            res = heal_feed(feed, recent_logs=[])
            self.assertEqual(res["status"], "healed")
            self.assertFalse(res["updates"]["disabled"])
            mock_client.update_feed.assert_called_once_with(4, disabled=False)

    def test_circuit_breaker_trips_after_3_attempts(self):
        feed = {
            "id": 5,
            "title": "Unstable Feed",
            "parsing_error_count": 4,
            "parsing_error_message": "Timeout deadline exceeded",
            "disabled": False,
        }
        now_iso = datetime.now(timezone.utc).isoformat()
        logs = [
            {"feed_id": 5, "healed_at": now_iso},
            {"feed_id": 5, "healed_at": now_iso},
            {"feed_id": 5, "healed_at": now_iso},
        ]
        res = heal_feed(feed, recent_logs=logs)
        self.assertEqual(res["status"], "tripped")
        self.assertEqual(res["action"], "circuit_breaker")


if __name__ == "__main__":
    unittest.main()
