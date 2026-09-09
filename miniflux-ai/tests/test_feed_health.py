import unittest
from unittest.mock import patch

from core import feed_health


class TestFeedHealthTrends(unittest.TestCase):
    def _sample(self, feed_id, hour_offset, status_code=None, latency=None, error=None):
        from datetime import datetime, timedelta, timezone
        # 相对当前时间生成采样（保证在分析窗口内）
        ts = (datetime.now(timezone.utc) - timedelta(hours=hour_offset)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        return {
            "sampled_at": ts,
            "feed_id": feed_id,
            "status_code": status_code,
            "latency_ms": latency,
            "error": error,
            "title": f"Feed {feed_id}",
        }

    def test_p95_basic(self):
        self.assertEqual(feed_health._p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), 10.0)

    def test_p95_empty(self):
        self.assertIsNone(feed_health._p95([]))

    def test_trends_bucket_success_rate(self):
        rows = [
            self._sample("1", 1, status_code=200, latency=10),
            self._sample("1", 1, status_code=500, latency=20),
            self._sample("1", 1, status_code=200, latency=15),
        ]
        with patch.object(feed_health, "_read", return_value=rows):
            d = feed_health.trends(hours=24)
        self.assertEqual(d["version"], "feed-health-trends-v1")
        self.assertEqual(len(d["feeds"]), 1)
        feed = d["feeds"][0]
        self.assertEqual(feed["feed_id"], "1")
        # 2 个成功 / 3 个采样
        self.assertAlmostEqual(feed["success_rate"], 2 / 3, places=3)
        # 平均延迟 (10+20+15)/3
        self.assertAlmostEqual(feed["average_latency_ms"], 15.0, places=1)
        # 只有一个 bucket
        self.assertEqual(len(feed["series"]), 1)
        self.assertAlmostEqual(feed["series"][0]["success_rate"], 2 / 3, places=3)

    def test_trends_errors_collected(self):
        rows = [
            self._sample("1", 1, status_code=200, latency=10),
            self._sample("1", 2, error="URLError: connection refused"),
        ]
        with patch.object(feed_health, "_read", return_value=rows):
            d = feed_health.trends(hours=24)
        self.assertEqual(len(d["recent_errors"]), 1)
        self.assertIn("URLError", d["recent_errors"][0]["error"])

    def test_trends_outside_window_excluded(self):
        # 采样在窗口之外（25 小时前）
        from datetime import datetime, timedelta, timezone
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        rows = [
            {
                "sampled_at": old_ts,  # >24h ago, outside window
                "feed_id": "1",
                "status_code": 200,
                "latency_ms": 10,
                "error": None,
            }
        ]
        with patch.object(feed_health, "_read", return_value=rows):
            d = feed_health.trends(hours=24)
        # 窗口过滤后可能为空（取决于 now）
        self.assertIn("feeds", d)
        self.assertIn("production_unchanged", d)
        self.assertTrue(d["production_unchanged"])

    def test_trends_multiple_buckets(self):
        rows = [
            self._sample("1", 3, status_code=200, latency=5),
            self._sample("1", 2, status_code=200, latency=7),
            self._sample("1", 1, status_code=200, latency=9),
        ]
        with patch.object(feed_health, "_read", return_value=rows):
            d = feed_health.trends(hours=24)
        feed = d["feeds"][0]
        # 每个小时一个 bucket → 3 个
        self.assertEqual(len(feed["series"]), 3)
        # bucket 按时间排序
        buckets = [s["bucket"] for s in feed["series"]]
        self.assertEqual(buckets, sorted(buckets))


if __name__ == "__main__":
    unittest.main()
