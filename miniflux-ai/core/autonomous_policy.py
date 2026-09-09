"""Pretrained-model-independent autonomous RSS routing policy.

The existing LLM Judge supplies content signals; this module turns them into
an explainable attention decision without requiring a human-labelled training
set. It never writes Miniflux or marks an article read.
"""
from __future__ import annotations

from typing import Any

VERSION = "autonomous-policy-v1"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def decide(row: dict[str, Any], source_quality: float = 50.0) -> dict[str, Any]:
    from core.rules_store import match_article_rules
    rule_match = match_article_rules(row)

    judge = row.get("judge") or {}
    taxonomy = judge.get("taxonomy") or row.get("taxonomy") or {}
    score = row.get("score")
    if not isinstance(score, (int, float)):
        return {
            "version": VERSION,
            "decision": "review",
            "label": "边界复核",
            "confidence": 0.45,
            "attention_score": None,
            "reasons": ["缺少有效评分"],
            "side_effects": False,
        }

    score = _clamp(_num(score))
    article_signals = row.get("article_signals") or {}
    freshness = _clamp(_num(article_signals.get("freshness"), 50.0))
    duplicate = bool(article_signals.get("duplicate"))
    interest = _clamp(_num(taxonomy.get("interest_match"), 50.0))
    promotion = _clamp(_num(judge.get("promotional")) / 5.0 * 100.0)
    low_content = _clamp(_num(judge.get("low_content")) / 5.0 * 100.0)
    entertainment = _clamp(_num(judge.get("entertainment_only")) / 5.0 * 100.0)
    source_quality = _clamp(_num(source_quality, 50.0))
    signal_confidence = _clamp(_num(row.get("confidence"), 0.72), 0.0, 1.0)

    title_str = str(row.get("title") or "").lower()
    if "digest for you" in title_str or row.get("feed_id") == 1:
        return {
            "version": VERSION,
            "decision": "priority" if score >= 60 else "keep",
            "label": "AI优先阅读" if score >= 60 else "AI正常保留",
            "confidence": 0.95,
            "attention_score": 85.0,
            "noise_score": 10.0,
            "freshness": freshness,
            "duplicate": False,
            "reasons": ["系统自建每日简报，原生保留"],
            "side_effects": False,
        }

    # 1. Rule Overrides take absolute precedence (Feedly/Inoreader style)
    if rule_match.get("muted"):
        reasons = rule_match.get("mute_reasons", [])
        if not reasons:
            reasons = ["命中用户静音与屏蔽规则"]
        return {
            "version": VERSION,
            "decision": "skip",
            "label": "AI静音/跳过",
            "confidence": 0.95,
            "attention_score": 10.0,
            "noise_score": 90.0,
            "freshness": freshness,
            "duplicate": duplicate,
            "reasons": reasons[:5],
            "side_effects": False,
            "muted_by_rule": True,
        }

    # If boosted by rule, boost attention and interest
    if rule_match.get("boosted"):
        interest = max(interest, 85.0)

    # If demoted by rule, penalize score and increase noise
    if rule_match.get("demoted"):
        score = max(0.0, score - 15.0)

    # Attention combines the existing quality score with explicit interest and
    # source reliability. It is deliberately not trained on human decisions.
    attention = 0.52 * score + 0.22 * interest + 0.14 * source_quality + 0.12 * freshness
    noise = 0.40 * (100.0 - score) + 0.25 * promotion + 0.18 * low_content + 0.05 * entertainment + (18.0 if duplicate else 0.0)
    margin = abs(attention - noise) / 100.0
    confidence = _clamp(100.0 * (0.55 * signal_confidence + 0.45 * (0.55 + 0.45 * min(1.0, margin * 2.0))), 45.0, 97.0) / 100.0

    reasons: list[str] = []
    if rule_match.get("boosted"):
        reasons.extend(rule_match.get("boost_reasons", []))
    if score >= 70:
        reasons.append(f"内容质量分 {score:.0f}/100")
    elif score < 35:
        reasons.append(f"内容质量分偏低 {score:.0f}/100")
    if interest >= 65:
        reasons.append(f"兴趣标签匹配 {interest:.0f}%")
    elif interest < 30:
        reasons.append(f"兴趣标签匹配偏低 {interest:.0f}%")
    if promotion >= 60:
        reasons.append(f"营销信号 {promotion:.0f}%")
    if low_content >= 60:
        reasons.append(f"低内容信号 {low_content:.0f}%")
    if duplicate:
        reasons.append("疑似重复文章")
    if freshness < 25:
        reasons.append("内容较旧")
    if source_quality >= 70:
        reasons.append(f"来源质量 {source_quality:.0f}/100")

    # Decision mapping:
    # 1. Genuine strong conflict -> review (minimized to true edge cases)
    if (score >= 68 and promotion >= 60) or (attention >= 65 and noise >= 65):
        decision = "review"
        label = "边界复核"
    # 2. Priority: High attention and low promo, or boosted by rule with good quality
    elif (attention >= 65 and promotion < 50 and low_content < 60) or (rule_match.get("boosted") and score >= 60 and promotion < 50):
        decision = "priority"
        label = "AI优先阅读"
    # 3. Skip: High noise + low score + marketing/low content, or duplicate
    elif (noise >= 65 and score < 40 and (promotion >= 40 or low_content >= 60)) or (score < 25 and (promotion >= 40 or low_content >= 60)) or (duplicate and noise >= 60):
        decision = "skip"
        label = "AI建议跳过"
    # 4. Default Keep: Normal reading stream, essays, blogs, cultural, technical
    else:
        decision = "keep"
        label = "AI正常保留"

    if not reasons:
        reasons.append("综合质量、兴趣和风险信号")
    return {
        "version": VERSION,
        "decision": decision,
        "label": label,
        "confidence": round(confidence, 3),
        "attention_score": round(_clamp(attention), 1),
        "noise_score": round(_clamp(noise), 1),
        "freshness": freshness,
        "duplicate": duplicate,
        "reasons": reasons[:5],
        "side_effects": False,
    }
