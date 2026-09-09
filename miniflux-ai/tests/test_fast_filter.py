import unittest

from core.fast_filter import evaluate_fast_path


class TestFastFilter(unittest.TestCase):
    def setUp(self):
        self.rules = {
            "boost_keywords": ["AI", "架构"],
            "boost_topics": ["技术"],
            "mute_keywords": ["领券", "包邮", "返利"],
            "mute_topics": ["消费"],
            "mute_content_types": ["deal"],
        }

    def test_whitelist_bypass_boost_keyword(self):
        # Entry has mute word "领券", but ALSO has boost word "AI" -> whitelist protects it!
        entry = {"title": "前沿AI智能体架构大促领券", "content_type": "news"}
        content = "详细技术分析正文..."
        triggered, result = evaluate_fast_path(entry, content, self.rules)
        self.assertFalse(triggered)
        self.assertIsNone(result)

    def test_whitelist_bypass_boost_topic(self):
        entry = {"title": "架构演进与技术突破", "content_type": "deal"}
        content = "技术正文..."
        triggered, result = evaluate_fast_path(entry, content, self.rules)
        self.assertFalse(triggered)
        self.assertIsNone(result)

    def test_fast_path_triggers_on_mute_keyword(self):
        entry = {"title": "超级大返利！限时特惠包邮", "content_type": "news"}
        content = "正文普通内容..."
        triggered, result = evaluate_fast_path(entry, content, self.rules)
        self.assertTrue(triggered)
        self.assertIsNotNone(result)
        self.assertEqual(result["score"], 10)
        self.assertTrue(result["fast_path"])
        self.assertEqual(result["pipeline_trace"]["stage"], "heuristic_fast_path")
        self.assertIn("命中屏蔽关键词: 返利", result["reason"])

    def test_fast_path_triggers_on_mute_content_type(self):
        entry = {"title": "普通商品推荐", "content_type": "deal"}
        content = "普通商品..."
        triggered, result = evaluate_fast_path(entry, content, self.rules)
        self.assertTrue(triggered)
        self.assertIn("内容类型已屏蔽: deal", result["reason"])

    def test_fast_path_triggers_on_short_promo(self):
        entry = {"title": "限时好物推荐秒杀中", "content_type": "other"}
        content = "短文本购买请点链接"  # < 120 chars + promo regex
        triggered, result = evaluate_fast_path(entry, content, self.rules)
        self.assertTrue(triggered)
        self.assertTrue(any("短文本" in r for r in result["judge"]["taxonomy"]["matched_keywords"]))

    def test_clean_article_passes_through_to_llm(self):
        entry = {"title": "古希腊哲学史浅析与城邦演化", "content_type": "opinion"}
        content = "这是一个长篇人文深度思考文章，探讨苏格拉底与柏拉图的政治哲学思想..." * 5
        triggered, result = evaluate_fast_path(entry, content, self.rules)
        self.assertFalse(triggered)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
