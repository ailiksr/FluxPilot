"""Recommendation ranking consistency check.

Validates that the recommendation list is strictly ordered by
recommended_score descending (the documented invariant from AI_HANDOVER.md
section 8.4: "Score 高 → Recommendation 排名靠前").  Read-only.
"""
from __future__ import annotations

VERSION = "recommendation-consistency-v1"


def check_consistency(items: list) -> dict:
    """Check that items are sorted by recommended_score descending.

    Args:
        items: list of recommendation dicts (each with recommended_score).

    Returns:
        dict with version, ok, violations (list), stats.
    """
    violations = []
    prev_score = None
    prev_entry = None
    for idx, item in enumerate(items):
        score = item.get("recommended_score")
        if not isinstance(score, (int, float)):
            violations.append({
                "index": idx,
                "entry_id": item.get("entry_id"),
                "issue": "missing_recommended_score",
                "score": None,
            })
            continue
        if prev_score is not None and score > prev_score:
            violations.append({
                "index": idx,
                "entry_id": item.get("entry_id"),
                "issue": "out_of_order",
                "score": score,
                "prev_score": prev_score,
                "prev_entry_id": prev_entry,
            })
        prev_score = score
        prev_entry = item.get("entry_id")

    scores = [x.get("recommended_score") for x in items
              if isinstance(x.get("recommended_score"), (int, float))]
    return {
        "version": VERSION,
        "production_unchanged": True,
        "ok": not violations,
        "violation_count": len(violations),
        "violations": violations,
        "stats": {
            "total": len(items),
            "scored": len(scores),
            "max_score": max(scores) if scores else None,
            "min_score": min(scores) if scores else None,
        },
    }
