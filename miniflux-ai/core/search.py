"""Full-text search across Miniflux entries, enriched with AI scores.

Read-only: searches Miniflux via its built-in search (title + content) and
merges the AI Worker's scoring data for entries that have been scored.

Hybrid strategy: Miniflux full-text search can be weak for Chinese/short
keywords (its tokenizer is English-oriented), so we additionally match the
scoring ledger's titles locally and merge both result sets.  Never mutates
Miniflux or writes anything.
"""
from __future__ import annotations

from common.logger import get_logger
from core.miniflux_client import get_miniflux_client

logger = get_logger(__name__)

SEARCH_VERSION = "search-v1"


def _ai_scores_map():
    """entry_id(str) -> {score, reason, scored_at, title} from scoring ledger."""
    out = {}
    try:
        from app.routes import _shared
        for r in _shared.read_scoring_rows():
            eid = r.get("entry_id")
            score = r.get("score")
            if eid is not None and isinstance(score, (int, float)):
                out[str(eid)] = {
                    "score": score,
                    "reason": r.get("reason"),
                    "scored_at": r.get("scored_at"),
                    "title": r.get("title"),
                }
    except Exception:
        logger.debug("AI score enrichment unavailable", exc_info=True)
    return out


def search_entries(query: str, limit: int = 20) -> dict:
    """Search Miniflux entries by keyword, enriched with AI scores.

    Args:
        query: search keyword.
        limit: max results (1-50).

    Returns:
        dict with version, query, count and items (each with AI score if scored).
    """
    query = (query or "").strip()
    limit = max(1, min(50, int(limit) if str(limit).isdigit() else 20))

    if not query:
        return {"version": SEARCH_VERSION, "query": query, "count": 0,
                "production_unchanged": True, "items": []}

    ai_scores = _ai_scores_map()

    # Channel 1: Miniflux full-text search
    entries = []
    try:
        result = get_miniflux_client().get_entries(search=query, limit=limit)
        entries = result.get("entries") or []
    except Exception as e:
        logger.warning(f"Miniflux search failed (falling back to local): {e}")

    # Channel 2: local scoring-ledger title match (helps Chinese keywords)
    q_lower = query.lower()
    local_matches = []
    for eid, ai in ai_scores.items():
        title = (ai.get("title") or "")
        if q_lower in title.lower() and not any(str(e.get("id")) == eid for e in entries):
            local_matches.append({
                "id": int(eid) if str(eid).isdigit() else eid,
                "title": title,
                "url": "",
                "feed_id": None,
                "status": "scored",
                "published_at": ai.get("scored_at"),
                "_local": True,
            })
    local_matches = local_matches[:max(0, limit - len(entries))]

    items = []
    for e in entries + local_matches:
        eid = e.get("id")
        ai = ai_scores.get(str(eid)) or {}
        items.append({
            "entry_id": eid,
            "title": e.get("title"),
            "url": e.get("url"),
            "feed_id": e.get("feed_id"),
            "status": e.get("status"),
            "published_at": e.get("published_at"),
            "ai_score": ai.get("score"),
            "ai_reason": ai.get("reason"),
            "ai_scored_at": ai.get("scored_at"),
            "source": "local" if e.get("_local") else "miniflux",
        })

    return {"version": SEARCH_VERSION, "query": query, "count": len(items),
            "production_unchanged": True, "items": items}
