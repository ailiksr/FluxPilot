import unittest

from core.rules_miner import mine_rule_suggestions


class TestRulesMiner(unittest.TestCase):
    def test_mine_rule_suggestions_mutes(self):
        rows = [
            {"title": "双11全网满减清单超值返利", "score": 20, "judge": {"promotional": 4, "content_type": "deal"}},
            {"title": "限时返利大促，手慢无", "score": 18, "judge": {"promotional": 5, "content_type": "deal"}},
            {"title": "全品类满减补贴汇总", "score": 22, "judge": {"promotional": 4, "content_type": "deal"}},
            {"title": "Python 异步编程实战与微服务架构", "score": 88, "judge": {"taxonomy": {"topics": ["技术"], "matched_keywords": ["Python", "微服务"]}}},
        ]
        rules = {
            "boost_keywords": ["Python"],
            "boost_topics": ["技术"],
            "mute_keywords": [],
            "mute_topics": [],
        }
        res = mine_rule_suggestions(rows, rules)
        self.assertIn("suggested_mutes", res)
        mute_words = [x["keyword"] for x in res["suggested_mutes"]]
        self.assertTrue("满减" in mute_words or "返利" in mute_words)

    def test_mine_rule_suggestions_boosts(self):
        rows = [
            {"title": "具身智能最新进展与工业落地", "score": 85, "judge": {"taxonomy": {"topics": ["具身智能"], "matched_keywords": ["具身智能", "机器人"]}}},
            {"title": "具身智能与大语言模型融合架构", "score": 82, "judge": {"taxonomy": {"topics": ["具身智能"], "matched_keywords": ["具身智能", "大模型"]}}},
            {"title": "无聊段子", "score": 40},
        ]
        rules = {
            "boost_keywords": ["大模型"],
            "boost_topics": [],
            "mute_keywords": [],
            "mute_topics": [],
        }
        res = mine_rule_suggestions(rows, rules)
        boost_words = [x["keyword"] for x in res["suggested_boosts"]]
        self.assertIn("具身智能", boost_words)

    def test_safety_check_excludes_terms_in_good_rows(self):
        rows = [
            {"title": "架构重构限时补贴大促", "score": 20, "judge": {"promotional": 4}},
            {"title": "架构重构补贴特惠", "score": 22, "judge": {"promotional": 4}},
            # "架构" is in a high-quality article!
            {"title": "大规模分布式系统架构设计原理", "score": 90, "judge": {"taxonomy": {"topics": ["架构"]}}},
        ]
        rules = {
            "boost_keywords": [],
            "boost_topics": [],
            "mute_keywords": [],
            "mute_topics": [],
        }
        res = mine_rule_suggestions(rows, rules)
        mute_words = [x["keyword"] for x in res["suggested_mutes"]]
        # "架构" should NOT be suggested as mute because it appears in a good row
        self.assertNotIn("架构", mute_words)


if __name__ == "__main__":
    unittest.main()
