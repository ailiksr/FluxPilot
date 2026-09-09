#!/usr/bin/env python3
"""Export PostgreSQL outbox events to JSONL backup files.

The application writes PostgreSQL domain data and an outbox event in one
transaction. This consumer is idempotent: if a process crashes after appending
but before marking an event exported, the payload hash prevents duplication on
the next run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg

DATA = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))
MAP = {
    "scoring_result": "scoring_results.jsonl",
    "review_event": "benchmark_reviews.jsonl",
    "taxonomy_feedback": "taxonomy_feedback.jsonl",
    "action_event": "feed_advice_actions.jsonl",
}


def payload_key(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def jsonl_has(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                if payload_key(json.loads(line)) == key:
                    return True
            except (json.JSONDecodeError, TypeError):
                continue
    except OSError:
        return False
    return False


def append(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> int:
    conn = psycopg.connect(
        host=os.environ.get("PGHOST", "postgres"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "miniflux"),
        user=os.environ.get("PGUSER", "miniflux"),
        password=os.environ.get("PGPASSWORD", ""),
        connect_timeout=5,
    )
    conn.autocommit = False
    exported = 0
    skipped = 0
    failed = 0
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT id,event_type,event_key,payload::text
                          FROM rss_ai_control.outbox_events
                          WHERE exported_at IS NULL
                          ORDER BY id
                          FOR UPDATE SKIP LOCKED
                          LIMIT 100""")
            events = cur.fetchall()
        for event_id, event_type, event_key, payload_text in events:
            try:
                payload = json.loads(payload_text)
                target_name = MAP.get(event_type)
                if not target_name:
                    raise ValueError(f"unknown event type: {event_type}")
                target = DATA / target_name
                if jsonl_has(target, event_key):
                    skipped += 1
                else:
                    append(target, payload)
                    skipped += 0
                with conn.cursor() as cur:
                    cur.execute("""UPDATE rss_ai_control.outbox_events
                                  SET exported_at=now(), attempts=attempts+1, last_error=NULL
                                  WHERE id=%s""", (event_id,))
                conn.commit()
                exported += 1
            except Exception as exc:
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute("""UPDATE rss_ai_control.outbox_events
                                  SET attempts=attempts+1, last_error=%s
                                  WHERE id=%s""", (str(exc)[:1000], event_id))
                conn.commit()
                failed += 1
    finally:
        conn.close()
    print(json.dumps({"exported": exported, "already_present": skipped, "failed": failed}, ensure_ascii=False))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
