"""Explainable RSS source quality and maintenance advice.

This is an AI-assisted, deterministic source health layer. It uses the existing
LLM Judge output and never changes Miniflux feed settings automatically.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean, pstdev
from typing import Any

VERSION = "feed-quality-v2"


def _quality_item(feed_id: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [r for r in rows if isinstance(r.get("score"), (int, float))]
    if not scored:
        return None
    scores = [float(r["score"]) for r in scored]
    latest = sorted(scored, key=lambda r: str(r.get("scored_at") or ""), reverse=True)
    half = max(1, len(scores) // 2)
    recent_avg = mean([float(r["score"]) for r in latest[:half]])
    older_avg = mean([float(r["score"]) for r in latest[half:]]) if len(scores) > half else recent_avg
    judges = [r.get("judge") or {} for r in scored]
    promotion_rate = mean(1.0 if float(j.get("promotional", 0) or 0) >= 3 else 0.0 for j in judges)
    low_content_rate = mean(1.0 if float(j.get("low_content", 0) or 0) >= 3 else 0.0 for j in judges)
    low_rate = mean(1.0 if score < 35 else 0.0 for score in scores)
    trend = recent_avg - older_avg
    volatility = pstdev(scores) if len(scores) > 1 else 0.0
    sample = len(scores)

    if sample < 3:
        action, label, priority = "observe", "样本不足·继续观察", "low"
    elif low_rate >= 0.70 and (promotion_rate >= 0.45 or low_content_rate >= 0.45):
        action, label, priority = "deprioritize", "建议降低优先级", "high"
    elif low_rate >= 0.45 or promotion_rate >= 0.50 or (volatility >= 28 and sample >= 5):
        action, label, priority = "observe", "建议观察", "medium"
    else:
        action, label, priority = "maintain", "保持当前优先级", "low"

    reasons = []
    if low_rate >= 0.45:
        reasons.append(f"低质量文章 {low_rate:.0%}")
    if promotion_rate >= 0.35:
        reasons.append(f"营销信号 {promotion_rate:.0%}")
    if low_content_rate >= 0.35:
        reasons.append(f"低内容信号 {low_content_rate:.0%}")
    if trend >= 8:
        reasons.append("近期质量上升")
    elif trend <= -8:
        reasons.append("近期质量下降")
    if volatility >= 28:
        reasons.append("内容质量波动较大")
    if not reasons:
        reasons.append("质量与风险信号处于可接受范围")

    confidence = min(0.95, 0.52 + min(0.30, sample / 30.0) + (0.10 if sample >= 5 else 0.0))
    return {
        "feed_id": feed_id,
        "version": VERSION,
        "action": action,
        "label": label,
        "priority": priority,
        "sample_size": sample,
        "average_score": round(mean(scores), 1),
        "recent_average": round(recent_avg, 1),
        "trend": round(trend, 1),
        "low_rate": round(low_rate, 3),
        "promotion_rate": round(promotion_rate, 3),
        "low_content_rate": round(low_content_rate, 3),
        "volatility": round(volatility, 1),
        "confidence": round(confidence, 3),
        "reasons": reasons[:5],
        "requires_approval": action == "deprioritize",
        "production_unchanged": True,
    }


def build_quality_report(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("feed_id") is not None:
            grouped[str(row["feed_id"])].append(row)
    result = []
    for feed_id, items in grouped.items():
        item = _quality_item(feed_id, items)
        if item:
            result.append(item)
    return sorted(result, key=lambda x: (x["priority"] != "high", -x["sample_size"], x["average_score"]))
