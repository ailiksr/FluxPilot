"""Best-effort real-time mirror from the JSONL event source to PostgreSQL.

JSONL remains the read-path fallback during migration. Mirror failures are
intentionally non-fatal so scoring and human review cannot be blocked by a
transient database/network problem; the hourly sync job repairs missed rows.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # Allows the legacy image to start during rollback.
    psycopg = None
    Jsonb = None

_ENABLED = os.environ.get("RSS_AI_PG_MIRROR_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
_LOCK = threading.Lock()
_CONN = None


def _connection():
    global _CONN
    if not _ENABLED or psycopg is None:
        return None
    if _CONN is not None and not _CONN.closed:
        return _CONN
    _CONN = psycopg.connect(
        host=os.environ.get("PGHOST", "postgres"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "miniflux"),
        user=os.environ.get("PGUSER", "miniflux"),
        password=os.environ.get("PGPASSWORD", ""),
        connect_timeout=3,
        autocommit=True,
    )
    return _CONN


def _execute(sql: str, params: tuple[Any, ...]) -> bool:
    global _CONN
    if not _ENABLED or psycopg is None:
        return False
    with _LOCK:
        try:
            conn = _connection()
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(sql, params)
            return True
        except Exception:
            if _CONN is not None:
                try:
                    _CONN.close()
                except Exception:
                    pass
                _CONN = None
            raise


def mirror_scoring_result(row: dict[str, Any]) -> bool:
    return _execute(
        """INSERT INTO rss_ai_control.scoring_results
        (entry_id,feed_id,title,content_hash,scored_at,score,base_score,feed_weight,
         recommend_score,judge,reason,confidence,attempt,error,score_version,calibration,raw)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING""",
        (
            row.get("entry_id"), row.get("feed_id"), row.get("title"),
            row.get("content_hash"), row.get("scored_at"), row.get("score"),
            row.get("base_score"), row.get("feed_weight"), row.get("recommend_score"),
            Jsonb(row.get("judge")) if Jsonb is not None and row.get("judge") is not None else None,
            row.get("reason"), row.get("confidence"), row.get("attempt"), row.get("error"),
            row.get("score_version"), row.get("calibration"), Jsonb(row),
        ),
    )


def mirror_review(row: dict[str, Any]) -> bool:
    return _execute(
        """INSERT INTO rss_ai_control.review_events
        (entry_id,status,category,human_score,score_range,notes,ai_recommendation,
         ai_confidence,reviewed_at,raw)
        SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        WHERE NOT EXISTS (SELECT 1 FROM rss_ai_control.review_events WHERE raw=%s)""",
        (
            row.get("entry_id"), row.get("status"), row.get("category"), row.get("human_score"),
            row.get("score_range"), row.get("notes"), row.get("ai_recommendation"),
            row.get("ai_confidence"), row.get("reviewed_at"), Jsonb(row), Jsonb(row),
        ),
    )


def mirror_taxonomy(row: dict[str, Any]) -> bool:
    return _execute(
        """INSERT INTO rss_ai_control.taxonomy_feedback (entry_id,taxonomy,updated_at,raw)
        SELECT %s,%s,%s,%s
        WHERE NOT EXISTS (SELECT 1 FROM rss_ai_control.taxonomy_feedback WHERE raw=%s)""",
        (row.get("entry_id"), Jsonb(row.get("taxonomy") or {}), row.get("updated_at"), Jsonb(row), Jsonb(row)),
    )


def mirror_action(row: dict[str, Any]) -> bool:
    advice = row.get("advice") or {}
    return _execute(
        """INSERT INTO rss_ai_control.action_events (action,occurred_at,advice,raw)
        SELECT %s,%s,%s,%s
        WHERE NOT EXISTS (SELECT 1 FROM rss_ai_control.action_events WHERE raw=%s)""",
        (row.get("action"), row.get("at"), Jsonb(advice), Jsonb(row), Jsonb(row)),
    )
