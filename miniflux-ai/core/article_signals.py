"""Read-only article noise signals backed by Miniflux PostgreSQL."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.storage import _connect

TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "source"}


def canonical_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        p = urlsplit(str(url).strip())
        host = (p.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in TRACKING_KEYS]
        path = p.path.rstrip("/") or "/"
        return urlunsplit((p.scheme.lower(), host, path, urlencode(query), ""))
    except Exception:
        return str(url).strip().lower()


def title_key(title: str | None) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(title or "")).lower()


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _age_hours(value: Any) -> float | None:
    if not value:
        return None
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds() / 3600.0)
    except Exception:
        return None


def enrich(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add duplicate/freshness fields without changing the source rows."""
    ids = [int(r["entry_id"]) for r in rows if str(r.get("entry_id", "")).isdigit()]
    if not ids:
        return rows
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,title,url,published_at,created_at,feed_id FROM entries WHERE id = ANY(%s)", (ids,))
                entries = {int(r[0]): {"title": r[1], "url": r[2], "published_at": r[3], "created_at": r[4], "feed_id": r[5]} for r in cur.fetchall()}
                cur.execute("SELECT id,parsing_error_count,parsing_error_msg,checked_at,next_check_at,disabled FROM feeds")
                feeds = {int(r[0]): {"parsing_error_count": r[1], "parsing_error_msg": r[2], "checked_at": r[3], "next_check_at": r[4], "disabled": r[5]} for r in cur.fetchall()}
    except Exception:
        return rows

    known = []
    for row in rows:
        eid = int(row["entry_id"]) if str(row.get("entry_id", "")).isdigit() else None
        e = entries.get(eid, {}) if eid is not None else {}
        text = title_key(e.get("title") or row.get("title"))
        url = canonical_url(e.get("url"))
        known.append((eid, text, url))
    result = []
    for row, (eid, text, url) in zip(rows, known):
        exact = next((other_id for other_id, other_text, other_url in known if other_id != eid and url and url == other_url), None)
        near = None
        near_score = 0.0
        if text:
            for other_id, other_text, other_url in known:
                if other_id == eid or not other_text:
                    continue
                value = similarity(text, other_text)
                if value > near_score:
                    near_score, near = value, other_id
        e = entries.get(eid, {}) if eid is not None else {}
        f = feeds.get(int(row.get("feed_id"))) or {}
        age = _age_hours(e.get("published_at") or e.get("created_at"))
        freshness = round(max(0.0, min(100.0, 100.0 * (0.5 ** (age / 48.0)))) if age is not None else 50.0, 1)
        duplicate = exact is not None or near_score >= 0.88
        result.append({**row, "article_signals": {"canonical_url": url, "exact_duplicate_of": exact, "similar_title_of": near if near_score >= 0.88 else None, "title_similarity": round(near_score, 3), "duplicate": duplicate, "freshness": freshness, "published_at": e.get("published_at")} , "feed_health": f})
    return result
