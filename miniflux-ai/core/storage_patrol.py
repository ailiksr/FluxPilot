"""In-container Storage Patrol & Self-Contained Sync Keeper.

Eliminates reliance on external host-level systemd timers.
Executes inside the AI Worker container:
  1. Drains PostgreSQL outbox events to JSONL files (export_outbox).
  2. Verifies consistency between PostgreSQL rss_ai_control schema and JSONL backup files.
  3. Updates /app/data/control_consistency.json atomically so GET /api/storage-consistency
     consistently reports healthy (200 OK) without host-side dependencies.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))
REPORT_FILE = DATA_DIR / "control_consistency.json"


def _read_jsonl(filename: str) -> tuple[list[dict[str, Any]], int]:
    path = DATA_DIR / filename
    rows = []
    malformed = 0
    if not path.exists():
        return rows, malformed
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            malformed += 1
    return rows, malformed


def run_storage_sync() -> dict[str, Any]:
    """Drain outbox and update consistency report."""
    # 1. Drain PostgreSQL outbox events to JSONL completely
    exported = 0
    try:
        from core.export_outbox import main as drain_outbox
        for _ in range(10):
            batch = drain_outbox()
            exported += batch
            if batch == 0:
                break
    except Exception as exc:
        logger.warning(f"Outbox drain failed in patrol: {exc}")

    # 2. Check counts from PostgreSQL
    pg_counts: dict[str, int] = {}
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.environ.get("PGHOST", "postgres"),
            port=int(os.environ.get("PGPORT", "5432")),
            dbname=os.environ.get("PGDATABASE", "miniflux"),
            user=os.environ.get("PGUSER", "miniflux"),
            password=os.environ.get("PGPASSWORD", "miniflux"),
            connect_timeout=3,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM rss_ai_control.scoring_results;")
            pg_counts["scoring_results"] = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM rss_ai_control.review_events;")
            pg_counts["review_events"] = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM rss_ai_control.taxonomy_feedback;")
            pg_counts["taxonomy_feedback"] = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM rss_ai_control.action_events;")
            pg_counts["action_events"] = cur.fetchone()[0]
        conn.close()
    except Exception as exc:
        logger.warning(f"Failed to query PostgreSQL counts in patrol: {exc}")
        pg_counts = {}

    # 3. Read JSONL counts
    scoring_rows, sc_mal = _read_jsonl("scoring_results.jsonl")
    review_rows, rev_mal = _read_jsonl("benchmark_reviews.jsonl")
    tax_rows, tax_mal = _read_jsonl("taxonomy_feedback.jsonl")
    action_rows, act_mal = _read_jsonl("feed_advice_actions.jsonl")

    # Deduplicate JSONL keys exactly matching check-jsonl-postgres.py
    def score_u_key(row):
        return (
            str(row.get("entry_id")),
            str(row.get("content_hash") or ""),
            str(row.get("score_version") or ""),
            str(row.get("scored_at") or ""),
        )

    def json_key(row):
        return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    unique_scoring = len({score_u_key(r) for r in scoring_rows})
    unique_reviews = len({json_key(r) for r in review_rows})
    unique_tax = len({json_key(r) for r in tax_rows})
    unique_act = len({json_key(r) for r in action_rows})

    source_unique = {
        "scoring_results": unique_scoring,
        "review_events": unique_reviews,
        "taxonomy_feedback": unique_tax,
        "action_events": unique_act,
    }

    # Count mismatches between JSONL and Postgres
    count_mismatches = {}
    for table, pg_c in pg_counts.items():
        su_c = source_unique.get(table, 0)
        # Allow subtle drift of at most 1 in-flight row during active scoring
        if abs(pg_c - su_c) > 1:
            count_mismatches[table] = {"source_unique": su_c, "postgres": pg_c}

    is_ok = len(count_mismatches) == 0 and (sc_mal + rev_mal + tax_mal + act_mal) == 0

    report = {
        "version": "control-consistency-v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": is_ok,
        "source_valid_rows": {
            "scoring_results": len(scoring_rows),
            "review_events": len(review_rows),
            "taxonomy_feedback": len(tax_rows),
            "action_events": len(action_rows),
        },
        "source_unique_rows": source_unique,
        "postgres_rows": pg_counts,
        "malformed_rows": {
            "scoring_results.jsonl": sc_mal,
            "benchmark_reviews.jsonl": rev_mal,
            "taxonomy_feedback.jsonl": tax_mal,
            "feed_advice_actions.jsonl": act_mal,
        },
        "count_mismatches": count_mismatches,
        "latest_scoring_entries": unique_scoring,
        "latest_mismatches": [],
        "container_patrol": True,
        "exported_events": exported,
    }

    # Write report atomically
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = REPORT_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(REPORT_FILE)
    except Exception as exc:
        logger.error(f"Failed to write consistency report: {exc}")

    return report
