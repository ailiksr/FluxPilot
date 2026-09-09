import unittest

from core.rules_store import (
    get_rules_hit_counts,
    get_rule_hits,
    simulate_rule,
    match_article_rules,
    DEFAULT_RULES,
)


class TestRulesSandbox(unittest.TestCase):
    def setUp(self):
        self.sample_rows = [
            {
                "entry_id": 1,
                "title": "全国酒店优惠券与返利汇总",
                "score": 25,
                "taxonomy": {"topics": ["消费"], "matched_keywords": ["优惠", "返利"]},
                "content": "正文省略...最后领取福利请点击链接",
            },
            {
                "entry_id": 2,
                "title": "深度剖析：新能源汽车税收优惠与补贴政策",
                "score": 85,
                "taxonomy": {"topics": ["财经", "新能源"], "matched_keywords": ["优惠", "补贴"]},
                "content": "深入政策分析正文内容...",
            },
            {
                "entry_id": 3,
                "title": "前沿AI大模型与智能体实战",
                "score": 92,
                "taxonomy": {"topics": ["AI", "技术"], "matched_keywords": ["AI", "智能体"]},
                "content": "技术干货...",
            },
            {
                "entry_id": 4,
                "title": "某最新旗舰手机开箱上手体验",
                "score": 60,
                "taxonomy": {"topics": ["数码"], "matched_keywords": ["开箱", "评测"]},
                "content": "外观很好看...",
            },
            {
                "entry_id": 5,
                "title": "职场技巧分享干货",
                "score": 70,
                "taxonomy": {"topics": ["职场"]},
                "content": "文章看似干货...文末福利：点击加微信免费领取试听课领券！",
            },
        ]

    def test_get_rules_hit_counts(self):
        rules = {
            "boost_keywords": ["AI", "智能体"],
            "boost_topics": ["技术"],
            "mute_keywords": ["返利", "领券"],
            "mute_topics": ["消费"],
            "demote_keywords": ["开箱"],
        }
        hits = get_rules_hit_counts(self.sample_rows, rules)
        self.assertEqual(hits["boost_keywords"]["AI"], 1)
        self.assertEqual(hits["boost_keywords"]["智能体"], 1)
        self.assertEqual(hits["mute_keywords"]["返利"], 1)
        # Entry 5 has "领券" in content tail:
        self.assertEqual(hits["mute_keywords"]["领券"], 1)
        self.assertEqual(hits["mute_topics"]["消费"], 1)
        self.assertEqual(hits["demote_keywords"]["开箱"], 1)

    def test_get_rule_hits(self):
        hits = get_rule_hits("AI", "boost_keyword", self.sample_rows)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["entry_id"], 3)

    def test_simulate_rule_safe_mute(self):
        # Muting "返利" only hits entry 1 (score 25), safe, no high-score warning
        res = simulate_rule("返利", "mute_kw", self.sample_rows)
        self.assertEqual(res["total_hits"], 1)
        self.assertEqual(res["high_score_count"], 0)
        self.assertEqual(res["low_score_count"], 1)
        self.assertIsNone(res["warning"])

    def test_simulate_rule_warns_on_high_score_false_positive(self):
        # Muting "优惠" hits entry 1 (score 25) AND entry 2 (score 85) -> triggers warning!
        res = simulate_rule("优惠", "mute_kw", self.sample_rows)
        self.assertEqual(res["total_hits"], 2)
        self.assertEqual(res["high_score_count"], 1)
        self.assertIsNotNone(res["warning"])
        self.assertIn("高分", res["warning"])

    def test_content_tail_scanning(self):
        # Entry 5 has a clean title, but tail content has "领券"
        rules = {
            "boost_keywords": [],
            "boost_topics": [],
            "mute_keywords": ["领券"],
            "mute_topics": [],
            "mute_content_types": [],
            "demote_keywords": [],
        }
        res = match_article_rules(self.sample_rows[4], rules)
        self.assertTrue(res["muted"])
        self.assertTrue(any("正文尾部" in r for r in res["mute_reasons"]))

    def test_soft_demote_keywords(self):
        # Entry 4 matches "开箱" -> demoted, not muted
        rules = {
            "boost_keywords": [],
            "boost_topics": [],
            "mute_keywords": [],
            "mute_topics": [],
            "mute_content_types": [],
            "demote_keywords": ["开箱"],
        }
        res = match_article_rules(self.sample_rows[3], rules)
        self.assertFalse(res["muted"])
        self.assertTrue(res["demoted"])
        self.assertTrue(any("降权" in r for r in res["demote_reasons"]))


if __name__ == "__main__":
    unittest.main()
