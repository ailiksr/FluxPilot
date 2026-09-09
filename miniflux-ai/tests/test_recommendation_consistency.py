import unittest

from core.recommendation_consistency import check_consistency


class TestRecommendationConsistency(unittest.TestCase):
    def test_sorted_descending_is_ok(self):
        items = [
            {"entry_id": 1, "recommended_score": 90},
            {"entry_id": 2, "recommended_score": 70},
            {"entry_id": 3, "recommended_score": 50},
        ]
        result = check_consistency(items)
        self.assertTrue(result["ok"])
        self.assertEqual(result["violation_count"], 0)

    def test_equal_scores_are_ok(self):
        items = [
            {"entry_id": 1, "recommended_score": 75},
            {"entry_id": 2, "recommended_score": 75},
            {"entry_id": 3, "recommended_score": 40},
        ]
        result = check_consistency(items)
        self.assertTrue(result["ok"])

    def test_out_of_order_detected(self):
        items = [
            {"entry_id": 1, "recommended_score": 50},
            {"entry_id": 2, "recommended_score": 90},
        ]
        result = check_consistency(items)
        self.assertFalse(result["ok"])
        self.assertEqual(result["violation_count"], 1)
        self.assertEqual(result["violations"][0]["entry_id"], 2)
        self.assertEqual(result["violations"][0]["issue"], "out_of_order")

    def test_missing_score_detected(self):
        items = [
            {"entry_id": 1, "recommended_score": 90},
            {"entry_id": 2},  # 无分数
        ]
        result = check_consistency(items)
        self.assertFalse(result["ok"])
        self.assertEqual(result["violations"][0]["issue"], "missing_recommended_score")

    def test_stats(self):
        items = [
            {"entry_id": 1, "recommended_score": 90},
            {"entry_id": 2, "recommended_score": 70},
        ]
        result = check_consistency(items)
        self.assertEqual(result["stats"]["total"], 2)
        self.assertEqual(result["stats"]["max_score"], 90)
        self.assertEqual(result["stats"]["min_score"], 70)
        self.assertTrue(result["production_unchanged"])

    def test_empty_list(self):
        result = check_consistency([])
        self.assertTrue(result["ok"])
        self.assertEqual(result["stats"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
