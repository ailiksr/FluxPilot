"""Transactional PostgreSQL control-plane writes for RSS AI.

When RSS_AI_WRITE_MODE=postgres, domain data and an outbox event are committed
in the same transaction. JSONL is exported asynchronously from the outbox and
is no longer part of the primary write path.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover
    psycopg = None
    Jsonb = None

_MODE = os.environ.get("RSS_AI_WRITE_MODE", "jsonl").strip().lower()
_ENABLED = _MODE == "postgres"
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def enabled() -> bool:
    return _ENABLED and psycopg is not None


def event_key(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _connect():
    if psycopg is None:
        raise RuntimeError("psycopg is unavailable")
    return psycopg.connect(
        host=os.environ.get("PGHOST", "postgres"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "miniflux"),
        user=os.environ.get("PGUSER", "miniflux"),
        password=os.environ.get("PGPASSWORD", ""),
        connect_timeout=5,
        autocommit=False,
    )


def ensure_schema(conn) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS rss_ai_control")
            cur.execute("""CREATE TABLE IF NOT EXISTS rss_ai_control.outbox_events (
                id BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_key TEXT NOT NULL UNIQUE,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                exported_at TIMESTAMPTZ,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS outbox_pending_idx ON rss_ai_control.outbox_events (id) WHERE exported_at IS NULL")
        conn.commit()
        _SCHEMA_READY = True


def _commit_event(conn, event_type: str, payload: dict[str, Any]) -> bool:
    key = event_key(payload)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO rss_ai_control.outbox_events (event_type,event_key,payload) VALUES (%s,%s,%s) ON CONFLICT (event_key) DO NOTHING",
            (event_type, key, Jsonb(payload)),
        )
    conn.commit()
    return True


def cached_scoring(entry_id: int, content_hash: str, score_version: str | None = None):
    """Return the latest matching PG score for scheduler idempotency."""
    if not enabled():
        return None
    with _connect() as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            if score_version:
                cur.execute("""SELECT raw::text FROM rss_ai_control.scoring_results
                    WHERE entry_id=%s AND content_hash=%s AND score_version=%s
                    ORDER BY scored_at DESC NULLS LAST, id DESC LIMIT 1""", (entry_id, content_hash, score_version))
            else:
                cur.execute("""SELECT raw::text FROM rss_ai_control.scoring_results
                    WHERE entry_id=%s AND content_hash=%s
                    ORDER BY scored_at DESC NULLS LAST, id DESC LIMIT 1""", (entry_id, content_hash))
            row = cur.fetchone()
            return json.loads(row[0]) if row else None


def persist_scoring(row: dict[str, Any]) -> bool:
    if not enabled():
        return False
    with _connect() as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO rss_ai_control.scoring_results
                (entry_id,feed_id,title,content_hash,scored_at,score,base_score,feed_weight,
                 recommend_score,judge,reason,confidence,attempt,error,score_version,calibration,raw)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING""", (
                row.get("entry_id"), row.get("feed_id"), row.get("title"), row.get("content_hash"),
                row.get("scored_at"), row.get("score"), row.get("base_score"), row.get("feed_weight"),
                row.get("recommend_score"), Jsonb(row.get("judge")) if row.get("judge") is not None else None,
                row.get("reason"), row.get("confidence"), row.get("attempt"), row.get("error"),
                row.get("score_version"), row.get("calibration"), Jsonb(row)))
        return _commit_event(conn, "scoring_result", row)


def persist_review(row: dict[str, Any]) -> bool:
    if not enabled():
        return False
    with _connect() as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO rss_ai_control.review_events
                (entry_id,status,category,human_score,score_range,notes,ai_recommendation,
                 ai_confidence,reviewed_at,raw)
                SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                WHERE NOT EXISTS (SELECT 1 FROM rss_ai_control.review_events WHERE md5(raw::text)=md5(%s::text))""", (
                row.get("entry_id"), row.get("status"), row.get("category"), row.get("human_score"),
                row.get("score_range"), row.get("notes"), row.get("ai_recommendation"),
                row.get("ai_confidence"), row.get("reviewed_at"), Jsonb(row), Jsonb(row)))
        return _commit_event(conn, "review_event", row)


def persist_taxonomy(row: dict[str, Any]) -> bool:
    if not enabled():
        return False
    with _connect() as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO rss_ai_control.taxonomy_feedback (entry_id,taxonomy,updated_at,raw)
                SELECT %s,%s,%s,%s
                WHERE NOT EXISTS (SELECT 1 FROM rss_ai_control.taxonomy_feedback WHERE md5(raw::text)=md5(%s::text))""", (
                row.get("entry_id"), Jsonb(row.get("taxonomy") or {}), row.get("updated_at"), Jsonb(row), Jsonb(row)))
        return _commit_event(conn, "taxonomy_feedback", row)


def persist_action(row: dict[str, Any]) -> bool:
    if not enabled():
        return False
    with _connect() as conn:
        ensure_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO rss_ai_control.action_events (action,occurred_at,advice,raw)
                SELECT %s,%s,%s,%s
                WHERE NOT EXISTS (SELECT 1 FROM rss_ai_control.action_events WHERE md5(raw::text)=md5(%s::text))""", (
                row.get("action"), row.get("at"), Jsonb(row.get("advice") or {}), Jsonb(row), Jsonb(row)))
        return _commit_event(conn, "action_event", row)


def status() -> dict[str, Any]:
    result = {"write_mode": _MODE, "postgres_driver": psycopg is not None}
    if not enabled():
        result["transactional_writes"] = False
        return result
    try:
        with _connect() as conn:
            ensure_schema(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM rss_ai_control.outbox_events WHERE exported_at IS NULL")
                result["outbox_pending"] = int(cur.fetchone()[0])
        result.update({"transactional_writes": True, "postgres_reachable": True})
    except Exception as exc:
        result.update({"transactional_writes": True, "postgres_reachable": False, "error_type": type(exc).__name__})
    return result
