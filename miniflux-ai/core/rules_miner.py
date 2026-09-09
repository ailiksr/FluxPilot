"""AI Rule Miner: Automatically discovers potential Mute and Boost rules from past scoring.

Inspired by Feedly Leo (Auto-Topics) and Inoreader Rules.
Scans low-quality / promotional articles to discover high-frequency junk keywords,
and scans high-quality articles to discover trending high-value topics not yet tracked.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from core.rules_store import load_rules

# Common promotional / e-commerce seed patterns to mine from titles
PROMO_SEEDS = [
    "满减", "秒杀", "返利", "立减", "大促", "福利", "特惠", "好价", "爆款",
    "补贴", "包邮", "实惠", "狂欢", "券后", "降价", "抽奖", "免单", "捡漏",
    "代金券", "微信群", "加群", "助手", "拼团", "淘客", "好物推荐", "抄底"
]

# Stop words to ignore when mining topics or terms
STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "年", "月", "日", "条", "第", "点",
    "更", "被", "为", "与", "及", "等", "如何", "为什么", "什么", "怎么",
    "资讯", "文章", "推荐", "分享", "今日", "最新", "大家", "可以", "我们"
}


def mine_rule_suggestions(rows: list[dict[str, Any]], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mine high-confidence suggestions for mute_keywords and boost_keywords."""
    if rules is None:
        rules = load_rules()

    active_mutes = {
        str(k).lower()
        for k in (rules.get("mute_keywords", []) + rules.get("mute_topics", []))
    }
    active_boosts = {
        str(k).lower()
        for k in (rules.get("boost_keywords", []) + rules.get("boost_topics", []))
    }

    trash_rows: list[dict[str, Any]] = []
    good_rows: list[dict[str, Any]] = []

    for r in rows:
        sc = r.get("score")
        judge = r.get("judge") or {}
        promo = judge.get("promotional") or 0
        ctype = str(judge.get("content_type") or "").lower()

        if (sc is not None and sc < 35) or promo >= 3 or ctype == "deal":
            trash_rows.append(r)
        elif sc is not None and sc >= 75:
            good_rows.append(r)

    # 1. Mute suggestions: find keywords prominent in trash_rows
    mute_counts: Counter[str] = Counter()
    mute_samples: dict[str, list[str]] = defaultdict(list)

    # A) Check promo seed keywords in titles
    for r in trash_rows:
        title = str(r.get("title") or "")
        title_low = title.lower()
        for seed in PROMO_SEEDS:
            seed_low = seed.lower()
            if seed_low in title_low and seed_low not in active_mutes:
                mute_counts[seed] += 1
                if len(mute_samples[seed]) < 3:
                    mute_samples[seed].append(title)

    # B) Check taxonomy keywords from trash articles
    for r in trash_rows:
        title = str(r.get("title") or "")
        judge = r.get("judge") or {}
        tax = judge.get("taxonomy") or r.get("taxonomy") or {}
        for kw in (tax.get("matched_keywords") or []):
            kw_str = str(kw).strip()
            kw_low = kw_str.lower()
            if len(kw_str) >= 2 and kw_low not in STOP_WORDS and kw_low not in active_mutes:
                mute_counts[kw_str] += 1
                if len(mute_samples[kw_str]) < 3 and title not in mute_samples[kw_str]:
                    mute_samples[kw_str].append(title)

    # Safety check: exclude terms that also appear in good_rows
    good_titles = " ".join(str(r.get("title") or "").lower() for r in good_rows)
    suggested_mutes = []
    for kw, cnt in mute_counts.most_common(12):
        if cnt < 2:
            continue
        if kw.lower() in good_titles:
            # Appeared in high-quality articles, unsafe to auto-mute
            continue
        suggested_mutes.append({
            "keyword": kw,
            "count": cnt,
            "sample_titles": mute_samples[kw][:2],
            "reason": f"在 {cnt} 篇低质或营销文章中频繁出现",
        })

    # 2. Boost suggestions: find topics and keywords prominent in good_rows
    boost_counts: Counter[str] = Counter()
    boost_samples: dict[str, list[str]] = defaultdict(list)

    for r in good_rows:
        title = str(r.get("title") or "")
        judge = r.get("judge") or {}
        tax = judge.get("taxonomy") or r.get("taxonomy") or {}
        candidates = list(tax.get("topics") or []) + list(tax.get("matched_keywords") or [])
        for item in candidates:
            item_str = str(item).strip()
            item_low = item_str.lower()
            if len(item_str) >= 2 and item_low not in STOP_WORDS and item_low not in active_boosts:
                boost_counts[item_str] += 1
                if len(boost_samples[item_str]) < 3 and title not in boost_samples[item_str]:
                    boost_samples[item_str].append(title)

    suggested_boosts = []
    for kw, cnt in boost_counts.most_common(10):
        if cnt < 1:
            continue
        suggested_boosts.append({
            "keyword": kw,
            "count": cnt,
            "sample_titles": boost_samples[kw][:2],
            "reason": f"在 {cnt} 篇高分精选好文中出现",
        })

    return {
        "version": "rules-suggestions-v1",
        "suggested_mutes": suggested_mutes[:8],
        "suggested_boosts": suggested_boosts[:8],
        "trash_sample_size": len(trash_rows),
        "good_sample_size": len(good_rows),
    }
