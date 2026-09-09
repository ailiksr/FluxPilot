"""Curated high-value article RSS feed.

Reference: newscope's custom filtered RSS feeds.  Generates an RSS feed of
the highest-scored articles from the AI scoring ledger, so users can
subscribe in any reader to "only the good stuff".

Read-only: never mutates Miniflux, never writes anything.  Only exposes
article title/link/summary — internal scoring dimensions are not included.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from common import config
from common.logger import get_logger
from feedgen.feed import FeedGenerator

logger = get_logger(__name__)

CURATED_URL = f"{config.digest_url}/rss/curated"


def generate_curated_rss(min_score: int = 70, limit: int = 30) -> str:
    """Generate an RSS feed of high-value articles from the scoring ledger.

    Args:
        min_score: minimum AI score (0-100) to include. Default 70.
        limit: maximum number of entries. Default 30.

    Returns:
        RSS XML content as string.
    """
    from app.routes import _shared

    rows = _shared.read_scoring_rows()
    # Deduplicate by entry_id, keep the latest row
    latest: dict = {}
    for r in rows:
        eid = r.get("entry_id")
        if eid is None:
            continue
        latest[str(eid)] = r

    scored = []
    for r in latest.values():
        score = r.get("score")
        title = (r.get("title") or "").strip()
        if not isinstance(score, (int, float)) or not title:
            continue
        if score < min_score:
            continue
        scored.append(r)

    scored.sort(key=lambda x: (x.get("score") or 0), reverse=True)
    scored = scored[:limit]

    feed = FeedGenerator()
    feed.id(CURATED_URL)
    feed.title(f"RSS AI 精选 · 高分文章 (≥{min_score})")
    feed.author({"name": "RSS AI Worker"})
    feed.subtitle("AI 评分筛选的高价值文章")
    feed.link(href=CURATED_URL, rel="self")

    # feedgen 会按 pubDate 倒序输出条目，因此这里按分数升序添加，
    # 最终 RSS 中即为分数降序（最高分在前）。
    for r in reversed(scored):
        eid = r.get("entry_id")
        score = r.get("score")
        title = r.get("title") or f"文章 #{eid}"
        link = r.get("url") or r.get("link") or ""
        reason = (r.get("reason") or "").strip()
        summary = f"AI 评分 {score}/100"
        if reason:
            summary += f" · {reason}"
        entry = feed.add_entry()
        entry.id(f"{CURATED_URL}/{eid}")
        if link:
            entry.link(href=link)
        entry.title(title)
        entry.description(summary)
        scored_at = r.get("scored_at")
        try:
            dt = datetime.fromisoformat(str(scored_at).replace("Z", "+00:00"))
            entry.pubDate(dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"))
        except Exception:
            entry.pubDate(time.strftime("%a, %d %b %Y %H:%M:%S +0000"))
        entry.author({"name": "RSS AI Worker"})

    logger.info("Generated curated RSS feed: %d entries (min_score=%d)", len(scored), min_score)
    rss = feed.rss_str(pretty=True)
    # feedgen may return bytes; normalize to str for consistent consumers/tests.
    return rss.decode("utf-8") if isinstance(rss, bytes) else rss
