"""Deterministic, read-only triage confidence for review workload reduction.
No LLM calls and no Miniflux writes occur here.
"""
from __future__ import annotations
import math

POSITIVE = ("information", "evidence", "depth", "timeliness", "originality", "practicality")
RISK = ("promotional", "entertainment_only", "low_content")

def triage_for(row: dict) -> dict:
    score = row.get("score")
    try: score = float(score)
    except (TypeError, ValueError): score = None
    j = row.get("judge") or {}
    vals = [float(j.get(k, 0)) for k in POSITIVE if isinstance(j.get(k, 0), (int,float))]
    risks = [float(j.get(k, 0)) for k in RISK if isinstance(j.get(k, 0), (int,float))]
    if not vals:
        return {"confidence": 0.45, "triage": "review", "triage_label": "需要人工判断", "triage_reason": "缺少完整 Judge 信号"}
    mean = sum(vals) / len(vals)
    spread = max(vals) - min(vals)
    variance = sum((x-mean)**2 for x in vals) / len(vals)
    agreement = max(0.0, 1.0 - math.sqrt(variance)/2.5)
    risk = sum(1 for x in risks if x >= 4)
    conflict = 0.12 if risk and score is not None and score >= 70 else 0.0
    confidence = max(0.45, min(0.97, 0.55 + 0.30*agreement + 0.10*(1 if all(0 <= x <= 5 for x in vals) else 0) - conflict))
    if score is None:
        bucket = "review"
    elif score < 20 and confidence >= 0.82 and mean <= 1.5 and risk == 0:
        bucket = "archive_candidate"
    elif score >= 80 and confidence >= 0.82 and mean >= 3.4 and risk == 0:
        bucket = "priority_candidate"
    else:
        bucket = "review"
    labels={"archive_candidate":"高置信低价值 · 建议归档","priority_candidate":"高置信高价值 · 优先阅读","review":"边界文章 · 需要人工判断"}
    return {"confidence": round(confidence,2), "triage": bucket, "triage_label": labels[bucket],
            "triage_reason": f"Judge一致性 {agreement:.0%} · 正向维度均值 {mean:.1f}/5 · 风险项 {risk} 个"}
