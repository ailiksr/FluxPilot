"""Controlled taxonomy for AI Worker article understanding (shadow mode).

This taxonomy is intentionally separate from article quality scoring. It is a
stable vocabulary used for future user-interest matching and ranking.
"""
VERSION = "taxonomy-v1"
CONTENT_TYPES = ("news", "analysis", "tutorial", "review", "opinion", "announcement", "deal", "entertainment", "other")
TOPICS = (
    "AI", "LLM", "Agent", "编程", "软件", "开源", "Linux", "Docker", "云计算",
    "互联网", "科技", "硬件", "消费", "商业", "金融", "投资", "汽车", "游戏",
    "影视", "文化", "健康", "科学", "社会", "国际", "国内", "职场", "设计", "安全"
)


def normalize_taxonomy(obj: dict | None) -> dict:
    obj = obj or {}
    c = obj.get("content_type", "other")
    if c not in CONTENT_TYPES:
        c = "other"
    topics = []
    for x in obj.get("topics", []) if isinstance(obj.get("topics", []), list) else []:
        if isinstance(x, str) and x in TOPICS and x not in topics:
            topics.append(x)
    return {
        "version": VERSION,
        "content_type": c,
        "topics": topics[:8],
        "matched_keywords": [str(x)[:40] for x in obj.get("matched_keywords", [])[:8]] if isinstance(obj.get("matched_keywords", []), list) else [],
        "interest_match": max(0, min(100, int(obj.get("interest_match", 0) or 0))),
    }


def taxonomy_status(judge: dict | None) -> str:
    """Return explicit status so old scores are distinguishable from tagged scores."""
    t = (judge or {}).get("taxonomy")
    return "complete" if isinstance(t, dict) and isinstance(t.get("interest_match"), (int, float)) else "missing"
