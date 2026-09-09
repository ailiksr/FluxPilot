"""Pre-LLM Fast-Path Heuristic Filter.

Evaluates incoming articles before invoking LLM scoring to save API tokens,
reduce latency, and avoid spending LLM computation on obvious promotional junk.

Safety Principles:
  1. Whitelist first: Articles matching user boost_keywords or boost_topics
     ALWAYS bypass fast-path rejection to ensure full LLM evaluation.
  2. Mute rules & extreme promotional patterns trigger instant local scoring (score=10~15).
  3. Every fast-path decision records a full `pipeline_trace` for 100% auditability.
"""
from __future__ import annotations

import re
from typing import Any
from common.logger import get_logger
from core.rules_store import match_article_rules

logger = get_logger(__name__)

# Extreme promotional patterns that, when combined with short content (<120 chars),
# trigger instant heuristic rejection without calling LLM.
EXTREME_PROMO_PATTERNS = [
    r"领[券劵]", r"包邮", r"返利", r"立减", r"买[一\d]送[一\d]", r"秒杀", r"津贴",
    r"抵扣券", r"优惠券", r"淘[口宝]令", r"拼团", r"好物推荐", r"满\d+减\d+"
]
PROMO_REGEX = re.compile("|".join(EXTREME_PROMO_PATTERNS), re.IGNORECASE)


def evaluate_fast_path(
    entry: dict[str, Any],
    clean_content: str,
    rules: dict[str, Any],
    score_version: str = "v23"
) -> tuple[bool, dict[str, Any] | None]:
    """Evaluate whether an entry can be immediately rejected by heuristic fast-path.

    Returns:
        (True, scoring_dict) if fast-path triggered.
        (False, None) if the entry should proceed to LLM scoring.
    """
    title = str(entry.get("title") or "").strip()
    title_low = title.lower()
    content_tail = clean_content[-500:].lower() if clean_content else ""

    # 1. Safety Whitelist: If title or content matches ANY boost rule, NEVER fast-path reject.
    boost_kws = [str(k).lower() for k in rules.get("boost_keywords", [])]
    boost_topics = [str(t).lower() for t in rules.get("boost_topics", [])]
    for bk in boost_kws:
        if bk in title_low:
            return False, None
    for bt in boost_topics:
        if bt in title_low:
            return False, None

    # 2. Macro Rule Match Check (hard mute keywords, mute topics, mute content types, tail scanning)
    rule_row = {
        "title": title,
        "content": clean_content,
        "taxonomy": {"matched_keywords": [], "topics": []},
        "judge": {"content_type": entry.get("content_type") or ""}
    }
    rule_match = match_article_rules(rule_row, rules)

    fast_reasons: list[str] = []
    if rule_match.get("muted"):
        fast_reasons.extend(rule_match.get("mute_reasons", []))

    # 3. Short Promotional Text Heuristic
    content_len = len(clean_content.strip())
    if content_len < 120 and PROMO_REGEX.search(title_low):
        fast_reasons.append("短文本(小于120字)且含密集营销导购特征")
    elif content_len < 60 and ("http" in content_tail or "点击" in content_tail or "购买" in content_tail):
        fast_reasons.append("极短文本(小于60字)且仅含外部跳转链接")

    if not fast_reasons:
        return False, None

    unique_reasons = list(dict.fromkeys(fast_reasons))
    fast_result: dict[str, Any] = {
        "judge": {
            "information": 1,
            "evidence": 1,
            "depth": 1,
            "timeliness": 3,
            "originality": 1,
            "practicality": 1,
            "promotional": 5,
            "entertainment_only": 1,
            "low_content": 4,
            "content_type": "deal",
            "taxonomy": {
                "topics": ["消费"],
                "matched_keywords": unique_reasons,
                "content_type": "deal"
            }
        },
        "score": 10,
        "base_score": 10,
        "reason": f"前置规则熔断: {'；'.join(unique_reasons)}",
        "confidence": 0.98,
        "attempt": 0,
        "score_version": score_version,
        "fast_path": True,
        "pipeline_trace": {
            "stage": "heuristic_fast_path",
            "fast_path": True,
            "base_score": 10,
            "final_score": 10,
            "rule_modifiers": [{"type": "fast_filter", "term": r, "impact": "mute"} for r in unique_reasons],
            "decision": "skip",
            "reasons": unique_reasons
        }
    }
    return True, fast_result
