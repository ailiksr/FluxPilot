"""V1 multi-dimensional scoring shadow model.

Quality is intentionally independent from user-interest relevance. Promotion and
other negative signals are a separate preference penalty. This module is pure
Python: no LLM calls and no Miniflux side effects.
"""
VERSION = "dimensions-v1"
QUALITY_WEIGHTS = {
    "information": 0.24,
    "evidence": 0.18,
    "depth": 0.18,
    "timeliness": 0.10,
    "originality": 0.14,
    "practicality": 0.16,
}
# Shadow-only defaults. Do not use for production ranking until calibrated.
DEFAULT_FINAL_WEIGHTS = {"quality": 0.45, "preference": 0.55}
DEFAULT_PREFERENCE_WEIGHTS = {"interest": 0.75, "anti_promotion": 0.25}


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(v)))


def quality_score(judge):
    vals = {k: float(judge.get(k, 0) or 0) for k in QUALITY_WEIGHTS}
    return round(_clamp(sum(QUALITY_WEIGHTS[k] * vals[k] / 5.0 * 100 for k in QUALITY_WEIGHTS)), 2)


def promotion_score(judge):
    return round(_clamp(float(judge.get("promotional", 0) or 0) / 5.0 * 100), 2)


def anti_promotion_score(judge):
    return round(100.0 - promotion_score(judge), 2)


def preference_score(taxonomy, judge):
    interest = _clamp((taxonomy or {}).get("interest_match", 0) or 0)
    anti = anti_promotion_score(judge or {})
    return round(DEFAULT_PREFERENCE_WEIGHTS["interest"] * interest + DEFAULT_PREFERENCE_WEIGHTS["anti_promotion"] * anti, 2)


def shadow_breakdown(row, learned_interest_correction=0, source_quality=50):
    judge = row.get("judge") or {}
    taxonomy = judge.get("taxonomy") or row.get("taxonomy")
    if not isinstance(taxonomy, dict) or "interest_match" not in taxonomy:
        return {"available": False, "version": VERSION, "reason": "taxonomy_missing"}
    quality = quality_score(judge)
    interest = _clamp(taxonomy.get("interest_match", 0))
    anti = anti_promotion_score(judge)
    correction = max(-25.0, min(25.0, float(learned_interest_correction or 0)))
    learned_interest = _clamp(interest + correction)
    preference = round(DEFAULT_PREFERENCE_WEIGHTS["interest"] * learned_interest + DEFAULT_PREFERENCE_WEIGHTS["anti_promotion"] * anti, 2)
    # V97 shadow-only source adjustment. Source quality is capped around neutral
    # and never writes feed policy.
    source_factor = max(0.85, min(1.05, float(source_quality or 50) / 50.0))
    final = DEFAULT_FINAL_WEIGHTS["quality"] * quality + DEFAULT_FINAL_WEIGHTS["preference"] * preference
    final = final * source_factor
    return {
        "available": True, "version": VERSION,
        "quality_score": quality,
        "interest_match": round(interest, 2),
        "learned_interest_correction": round(correction, 2),
        "learned_interest": round(learned_interest, 2),
        "promotion_score": promotion_score(judge),
        "anti_promotion_score": anti,
        "preference_score": preference,
        "source_quality": round(float(source_quality or 50),2),
        "source_factor": round(source_factor,3),
        "final_shadow_score": round(_clamp(final), 2),
        "decision_reasons": {
            "positive": [x for x in [
                "质量评分较高" if quality >= 70 else None,
                "兴趣主题命中" if learned_interest >= 60 else None,
            ] if x],
            "negative": [x for x in [
                "营销信号较高" if promotion_score(judge) >= 60 else None,
                "兴趣证据不足" if learned_interest < 40 else None,
            ] if x],
        },
        "weights": {"quality": DEFAULT_FINAL_WEIGHTS["quality"], "preference": DEFAULT_FINAL_WEIGHTS["preference"], **DEFAULT_PREFERENCE_WEIGHTS},
    }
