import unittest
from core.rules_store import load_rules, save_rules, apply_rules, DEFAULT_RULES
from core.autonomous_policy import decide
from core.pre_review import pre_review_item

class TestRulesStore(unittest.TestCase):
    def test_default_rules(self):
        rules = load_rules()
        self.assertIn("AI", rules.get("boost_keywords", []))
        self.assertIn("deal", rules.get("mute_content_types", []))
        self.assertIn("折扣", rules.get("mute_keywords", []))

    def test_apply_rules_mute_keyword(self):
        row = {"title": "超级大折扣！", "score": 80, "taxonomy": {"matched_keywords": ["折扣"]}}
        res = apply_rules(row, DEFAULT_RULES)
        self.assertTrue(res["muted"])
        self.assertFalse(res["boosted"])
        self.assertTrue(any("折扣" in r for r in res["mute_reasons"]))

    def test_apply_rules_boost_keyword(self):
        row = {"title": "前沿AI架构演进", "score": 60, "taxonomy": {"matched_keywords": ["AI"], "topics": ["技术"]}}
        res = apply_rules(row, DEFAULT_RULES)
        self.assertTrue(res["boosted"])
        self.assertFalse(res["muted"])
        self.assertTrue(any("AI" in r for r in res["boost_reasons"]))

    def test_apply_rules_mute_content_type(self):
        row = {"title": "好物推荐", "score": 90, "judge": {"content_type": "deal"}}
        res = apply_rules(row, DEFAULT_RULES)
        self.assertTrue(res["muted"])
        self.assertTrue(any("deal" in r for r in res["mute_reasons"]))

    def test_autonomous_policy_with_mute(self):
        row = {"title": "限时特惠促销领券", "score": 85, "judge": {"taxonomy": {"matched_keywords": ["促销", "领券"]}}}
        dec = decide(row)
        self.assertEqual(dec["decision"], "skip")
        self.assertFalse(dec["side_effects"])
        self.assertTrue(any("屏蔽" in r for r in dec["reasons"]))

    def test_pre_review_item_with_mute_and_boost(self):
        muted = {"title": "促销返利优惠", "score": 75, "judge": {"taxonomy": {"matched_keywords": ["促销"]}}}
        res_m = pre_review_item(muted)
        self.assertEqual(res_m["suggestion"], "archive")

        boosted = {"title": "AI与大模型系统实战", "score": 65, "judge": {"taxonomy": {"matched_keywords": ["AI", "大模型"]}}}
        res_b = pre_review_item(boosted)
        self.assertEqual(res_b["suggestion"], "keep")

if __name__ == "__main__":
    unittest.main()
