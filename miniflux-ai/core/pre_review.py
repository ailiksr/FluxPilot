"""Algorithmic pre-review (triage) of the human review queue.

Reference: Readwise Reader inbox triage, Inoreader rule filters, and the
project's own autonomous policy signals.  This produces a *pre-review*
suggestion (keep / archive / boundary) using deterministic signals — no LLM
call, no Miniflux write — so a human reviewer can confirm or override
quickly.

Signals used:
  - ai_score            (0-100)      overall AI quality
  - promotional         (0-5)        marketing/ad signal
  - low_content         (0-5)        low-content signal
  - interest_match      (0-100)      user-interest tag match
  - content_type        deal/entertainment get a small deduction
  - autonomous.reasons  existing explainable signals
"""
from __future__ import annotations

VERSION = "pre-review-v1"

# Statuses that count as "already decided" (excluded from pending/pre-review).
DONE_STATUSES = {"keep", "archive", "ignore", "executed"}


def _num(v, default=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def score_article(row: dict) -> dict:
    """Compute a pre-review score and suggestion for one article row."""
    score = _num(row.get("score"))
    judge = row.get("judge") or {}
    title = str(row.get("title") or "")

    # System Digest Immunity: Never mute or archive automated briefings
    if "digest for you" in title.lower() or row.get("feed_id") == 1:
        return {
            "entry_id": row.get("entry_id"),
            "title": title,
            "ai_score": score,
            "pre_review_score": max(65, int(round(score))),
            "suggestion": "keep",
            "label": "建议保留",
            "reasons": ["⭐ 自动化系统简报，原生保留"],
            "judge": judge,
            "production_unchanged": True,
        }

    from core.rules_store import match_article_rules
    rule_match = match_article_rules(row)

    promo = _num(judge.get("promotional"))
    low_content = _num(judge.get("low_content"))
    interest = _num(judge.get("interest_match"), 50)
    ctype = str(judge.get("content_type") or "other")

    # Base recommendation score: AI score is primary.
    rec = score

    # Deductions
    if promo >= 4:
        rec -= 15
    elif promo >= 3:
        rec -= 8
    if low_content >= 4:
        rec -= 10
    elif low_content >= 3:
        rec -= 5
    # Type deduction: deal (促销) and entertainment-only content
    if ctype in ("deal", "entertainment"):
        rec -= 6
    # Interest bonus if strong match
    if interest >= 70:
        rec += 8

    # Apply user active rules (highest priority)
    reasons = []
    if rule_match.get("muted"):
        rec = min(rec, 15)
        for mr in rule_match.get("mute_reasons", []):
            reasons.append(f"🔴 {mr}")
    elif rule_match.get("demoted"):
        rec = max(0, rec - 15)
        for dr in rule_match.get("demote_reasons", []):
            reasons.append(f"🟡 {dr}")
    elif rule_match.get("boosted"):
        rec = min(100, rec + 15)
        for br in rule_match.get("boost_reasons", []):
            reasons.append(f"🟢 {br}")

    rec = max(0, min(100, round(rec)))

    # Suggestion mapping: Muted rules force archive
    if rule_match.get("muted") or (rec < 25 and (promo >= 3 or low_content >= 3)):
        suggestion = "archive"
        label = "建议归档"
    elif rec >= 60 and promo < 3 and low_content < 3:
        suggestion = "keep"
        label = "建议保留"
    else:
        suggestion = "boundary"
        label = "边界需人工"

    if promo >= 4:
        reasons.append(f"营销信号高 ({int(promo)}/5)")
    if low_content >= 4:
        reasons.append(f"低内容信号高 ({int(low_content)}/5)")
    if ctype == "deal":
        reasons.append("内容类型: 促销/优惠")
    if interest >= 70:
        reasons.append(f"兴趣标签匹配 {int(interest)}%")
    elif interest < 30:
        reasons.append(f"兴趣标签匹配低 ({int(interest)}%)")
    reasons.append(f"AI 评分 {int(score)}")

    return {
        "entry_id": row.get("entry_id"),
        "title": row.get("title"),
        "ai_score": int(score),
        "promotional": int(promo),
        "low_content": int(low_content),
        "interest_match": int(interest),
        "content_type": ctype,
        "pre_review_score": rec,
        "suggestion": suggestion,
        "label": label,
        "reasons": reasons[:5],
        "production_unchanged": True,
    }


def pre_review_items(rows: list) -> dict:
    """Pre-review a batch of rows; group by suggestion."""
    items = [score_article(r) for r in rows]
    groups = {"keep": [], "archive": [], "boundary": []}
    for x in items:
        groups[x["suggestion"]].append(x)
    return {
        "version": VERSION,
        "total": len(items),
        "counts": {k: len(v) for k, v in groups.items()},
        "items": items,
        "production_unchanged": True,
    }


pre_review_item = score_article