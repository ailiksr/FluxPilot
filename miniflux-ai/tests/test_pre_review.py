import unittest

from core.pre_review import score_article, pre_review_items


def _row(eid, score=50, promo=0, low=0, interest=50, ctype="news", title="t"):
    return {
        "entry_id": eid, "title": title, "score": score,
        "judge": {"promotional": promo, "low_content": low,
                  "interest_match": interest, "content_type": ctype},
    }


class TestPreReview(unittest.TestCase):
    def test_high_promo_low_score_archive(self):
        r = score_article(_row(1, score=20, promo=5, low=4))
        self.assertEqual(r["suggestion"], "archive")
        self.assertLessEqual(r["pre_review_score"], r["ai_score"])

    def test_high_score_clean_keep(self):
        r = score_article(_row(2, score=80, promo=0, low=0))
        self.assertEqual(r["suggestion"], "keep")

    def test_deal_type_deducted(self):
        r = score_article(_row(3, score=70, promo=2, low=1, ctype="deal"))
        # deal 类型默认在屏蔽规则中，因此直接触发建议归档
        self.assertEqual(r["suggestion"], "archive")
        self.assertIn("内容类型已屏蔽", r["reasons"][0])

    def test_boundary_when_mixed(self):
        r = score_article(_row(4, score=50, promo=2, low=2, ctype="news"))
        self.assertEqual(r["suggestion"], "boundary")

    def test_interest_bonus(self):
        r = score_article(_row(5, score=60, promo=0, low=0, interest=80))
        # 60 + 8(兴趣) = 68 → keep
        self.assertEqual(r["suggestion"], "keep")
        self.assertEqual(r["pre_review_score"], 68)

    def test_batch_groups(self):
        rows = [
            _row(1, score=20, promo=5, low=4),
            _row(2, score=85, promo=0, low=0),
            _row(3, score=50, promo=1, low=1),
        ]
        result = pre_review_items(rows)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["counts"]["archive"], 1)
        self.assertEqual(result["counts"]["keep"], 1)
        self.assertEqual(result["counts"]["boundary"], 1)
        self.assertTrue(result["production_unchanged"])

    def test_all_production_unchanged_flags(self):
        rows = [_row(i, score=40 + i * 10, promo=1, low=1) for i in range(3)]
        for x in pre_review_items(rows)["items"]:
            self.assertTrue(x["production_unchanged"])


if __name__ == "__main__":
    unittest.main()
