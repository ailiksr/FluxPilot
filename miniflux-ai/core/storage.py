"""Storage read adapter for the JSONL -> PostgreSQL migration.

Modes:
- jsonl: JSONL is authoritative (default).
- dual: return JSONL and compare the PostgreSQL mirror read-only.
- postgres: return PostgreSQL, falling back to JSONL on any read failure.

Action events are append-only audit data, so they are read from the table
directly rather than through a latest-row view.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

try:
    import psycopg
except ImportError:  # legacy image / emergency rollback
    psycopg = None

LOGGER = logging.getLogger(__name__)
MODE = os.environ.get("RSS_AI_STORAGE_MODE", "jsonl").strip().lower()
if MODE not in {"jsonl", "dual", "postgres"}:
    LOGGER.warning("Unknown RSS_AI_STORAGE_MODE=%r; using jsonl", MODE)
    MODE = "jsonl"


def _connect():
    if psycopg is None:
        raise RuntimeError("psycopg is unavailable")
    return psycopg.connect(
        host=os.environ.get("PGHOST", "postgres"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "miniflux"),
        user=os.environ.get("PGUSER", "miniflux"),
        password=os.environ.get("PGPASSWORD", ""),
        connect_timeout=3,
        autocommit=True,
    )


def _query_raw(view: str) -> list[dict[str, Any]]:
    if view == "action_events":
        query = "SELECT raw::text FROM rss_ai_control.action_events ORDER BY occurred_at ASC NULLS LAST, id ASC"
    elif view in {"latest_scoring_results", "latest_review_events", "latest_taxonomy_feedback"}:
        query = f"SELECT raw::text FROM rss_ai_control.{view}"
    else:
        raise ValueError("invalid storage view")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = []
            for (raw,) in cur.fetchall():
                if isinstance(raw, str):
                    rows.append(json.loads(raw))
                elif isinstance(raw, dict):
                    rows.append(raw)
            return rows


def _identity(rows: list[dict[str, Any]], kind: str) -> set[tuple[str, ...]]:
    if kind == "scoring":
        return {
            (str(row.get("entry_id")), str(row.get("content_hash") or ""),
             str(row.get("score_version") or ""))
            for row in rows
        }
    return {
        (str(row.get("entry_id")), json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        for row in rows
    }


def _read(kind: str, fallback: Callable[[], Any], view: str):
    jsonl_rows = fallback()
    if MODE == "jsonl":
        return jsonl_rows
    try:
        pg_rows = _query_raw(view)
        if MODE == "dual":
            left = _identity(jsonl_rows, kind)
            right = _identity(pg_rows, kind)
            if left != right:
                LOGGER.warning(
                    "storage dual-read mismatch kind=%s jsonl=%d postgres=%d only_jsonl=%d only_postgres=%d",
                    kind, len(left), len(right), len(left - right), len(right - left),
                )
            return jsonl_rows
        return pg_rows
    except Exception as exc:
        LOGGER.warning("PostgreSQL read failed kind=%s; falling back to JSONL: %s", kind, exc)
        return jsonl_rows


def read_scoring(fallback):
    return _read("scoring", fallback, "latest_scoring_results")


def read_reviews(fallback):
    rows = _read("reviews", fallback, "latest_review_events")
    return {str(row.get("entry_id")): row for row in rows}


def read_taxonomy(fallback):
    rows = _read("taxonomy", fallback, "latest_taxonomy_feedback")
    return {str(row.get("entry_id")): row for row in rows}


def read_actions(fallback):
    """Read the complete append-only action audit stream."""
    return _read("actions", fallback, "action_events")


def status() -> dict[str, Any]:
    """Return read-only adapter status without exposing connection details."""
    result: dict[str, Any] = {"mode": MODE, "postgres_driver": psycopg is not None}
    if MODE == "jsonl":
        result["read_source"] = "jsonl"
        return result
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        result.update({"postgres_reachable": True, "read_source": "jsonl" if MODE == "dual" else "postgres"})
    except Exception as exc:
        result.update({"postgres_reachable": False, "read_source": "jsonl", "error_type": type(exc).__name__})
    return result
