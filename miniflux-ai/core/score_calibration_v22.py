"""V22 deterministic score calibration and explainability helpers.

The LLM only produces the 0..5 Judge dimensions. This module is deterministic:
it maps the weighted quality signal onto a semantic 10..90 scale and applies
small, bounded type penalties. It deliberately does not normalize against the
current dataset, so scores remain comparable across time.
"""
from __future__ import annotations

WEIGHTS = {
    "information": 0.24,
    "evidence": 0.18,
    "depth": 0.18,
    "timeliness": 0.10,
    "originality": 0.14,
    "practicality": 0.16,
}
PENALTIES = {
    "promotional": 0.60,
    "entertainment_only": 0.25,
    "low_content": 0.40,
}
VERSION = "v22"


def _weighted_quality(judge: dict) -> float:
    return sum(WEIGHTS[k] * float(judge[k]) for k in WEIGHTS)


def score_breakdown(judge: dict) -> dict:
    quality = _weighted_quality(judge)
    base = 10.0 + 16.0 * quality
    penalties = {k: PENALTIES[k] * float(judge.get(k, 0)) for k in PENALTIES}
    total_penalty = sum(penalties.values())
    empty_core = all(float(judge.get(k, 0)) == 0 for k in WEIGHTS)
    raw = base - total_penalty
    if empty_core:
        raw = min(raw, 18.0)
    final = max(10.0, min(90.0, raw))
    return {
        "quality": round(quality, 4),
        "base_score": round(base, 2),
        "penalties": {k: round(v, 2) for k, v in penalties.items()},
        "penalty_total": round(total_penalty, 2),
        "raw_score": round(raw, 2),
        "score": int(round(final)),
        "score_version": VERSION,
    }


def score(judge: dict) -> int:
    return score_breakdown(judge)["score"]
