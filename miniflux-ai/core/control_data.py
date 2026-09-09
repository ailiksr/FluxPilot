"""Shared control-plane data access helpers for the API layer.

These helpers centralise JSONL fallback reading and PostgreSQL write-through
so that route modules do not each re-implement file paths, locks and storage
adapter calls.  They do not change any production safety boundary: writes to
PostgreSQL remain transactional via the outbox, and JSONL stays the fallback.
"""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))
SCORING_DATA = DATA_DIR / "scoring_results.jsonl"
BENCHMARK_DATA = DATA_DIR / "benchmark_reviews.jsonl"
ACTION_DATA = DATA_DIR / "feed_advice_actions.jsonl"
TAXONOMY_DATA = DATA_DIR / "taxonomy_feedback.jsonl"
_JSONL_LOCK = DATA_DIR / ".jsonl.lock"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return rows


def read_scoring() -> list[dict[str, Any]]:
    """Read the latest scoring rows from the configured control-plane source."""
    latest: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(SCORING_DATA):
        eid = row.get("entry_id")
        if eid is not None:
            latest[str(eid)] = row
    rows = sorted(latest.values(), key=lambda x: x.get("scored_at", ""), reverse=True)
    try:
        from core.storage import read_scoring as _read_scoring
        return _read_scoring(lambda: rows)
    except Exception:
        return rows


def read_scoring_by_id() -> dict[str, dict[str, Any]]:
    return {str(r.get("entry_id")): r for r in read_scoring()}


def feed_quality_map() -> dict[str, float]:
    result: dict[str, list[float]] = {}
    for r in read_scoring():
        fid = r.get("feed_id")
        score = r.get("score")
        if fid is None or not isinstance(score, (int, float)):
            continue
        result.setdefault(str(fid), []).append(score)
    return {fid: sum(vals) / len(vals) for fid, vals in result.items()}


def read_reviews() -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(BENCHMARK_DATA)
    try:
        from core.storage import read_reviews as _read_reviews
        return _read_reviews(lambda: rows)
    except Exception:
        return {str(r.get("entry_id")): r for r in rows}


def read_taxonomy() -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(TAXONOMY_DATA)
    try:
        from core.storage import read_taxonomy as _read_taxonomy
        return _read_taxonomy(lambda: rows)
    except Exception:
        return {str(r.get("entry_id")): r for r in rows}


def read_actions() -> list[dict[str, Any]]:
    try:
        from core.storage import read_actions as _read_actions
        return _read_actions(lambda: _read_jsonl(ACTION_DATA))
    except Exception:
        return _read_jsonl(ACTION_DATA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_review(row: dict[str, Any]) -> None:
    try:
        from core.control_store import enabled as pg_write_enabled, persist_review
        if pg_write_enabled():
            persist_review(row)
            return
    except Exception:
        raise
    _append_jsonl(BENCHMARK_DATA, row)
    try:
        from core.pg_mirror import mirror_review
        mirror_review(row)
    except Exception:
        pass


def write_taxonomy(feedback: dict[str, Any]) -> None:
    try:
        from core.control_store import enabled as pg_write_enabled, persist_taxonomy
        if pg_write_enabled():
            persist_taxonomy(feedback)
            return
    except Exception:
        raise
    _append_jsonl(TAXONOMY_DATA, feedback)
    try:
        from core.pg_mirror import mirror_taxonomy
        mirror_taxonomy(feedback)
    except Exception:
        pass


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _JSONL_LOCK.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def clean_list(value, limit=8, max_len=40):
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        x = str(x).strip()
        if x and x not in out:
            out.append(x[:max_len])
    return out[:limit]


def utc_now() -> str:
    return _now()
