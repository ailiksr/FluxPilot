"""Shared data-access helpers and path constants for route modules.

Extracted from scoring.py during V131 route modularisation.  All route
modules that need to read/write the scoring ledger, benchmark reviews or
audit actions import from here so the Blueprint owner (scoring.py) stays
the single registration surface while the helpers are owned centrally.
"""
import fcntl
import json
import os
from pathlib import Path

from flask import jsonify

# ---------------------------------------------------------------------------
# Data path constants
# ---------------------------------------------------------------------------
_DATA_DIR = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))

DATA = _DATA_DIR / "scoring_results.jsonl"
ACTION_DATA = _DATA_DIR / "feed_advice_actions.jsonl"
BENCHMARK_DATA = _DATA_DIR / "benchmark_reviews.jsonl"
TAXONOMY_FEEDBACK_DATA = _DATA_DIR / "taxonomy_feedback.jsonl"
_JSONL_LOCK = _DATA_DIR / ".jsonl.lock"


# ---------------------------------------------------------------------------
# Canonical response envelope
# ---------------------------------------------------------------------------
def api_response(version, **payload):
    """Canonical response envelope for migrated routes; legacy routes stay byte-compatible."""
    return jsonify({"version": version, **payload})


# ---------------------------------------------------------------------------
# Scoring ledger helpers
# ---------------------------------------------------------------------------
def read_scoring_rows():
    """Read the latest scoring row per entry_id, preferring PostgreSQL, falling back to JSONL."""
    if not DATA.exists():
        return []
    latest = {}
    for line in DATA.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            latest[str(row["entry_id"])] = row
        except Exception:
            continue
    rows = sorted(latest.values(), key=lambda x: x.get("scored_at", ""), reverse=True)
    try:
        from core.storage import read_scoring
        return read_scoring(lambda: rows)
    except Exception:
        return rows


def feed_quality_map():
    """Average score per feed_id from the current scoring ledger."""
    rows = read_scoring_rows()
    sums = {}
    for r in rows:
        fid = r.get("feed_id")
        score = r.get("score")
        if fid is None or not isinstance(score, (int, float)):
            continue
        sums.setdefault(str(fid), []).append(score)
    return {fid: sum(vals) / len(vals) for fid, vals in sums.items()}


def read_actions():
    """Read audit actions from the configured control-plane source."""
    def fallback():
        if not ACTION_DATA.exists():
            return []
        rows = []
        for line in ACTION_DATA.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        return rows

    try:
        from core.storage import read_actions
        return read_actions(fallback)
    except Exception:
        return fallback()


# ---------------------------------------------------------------------------
# Benchmark review helpers
# ---------------------------------------------------------------------------
def read_benchmark_reviews():
    """Read benchmark reviews keyed by entry_id, preferring PostgreSQL, falling back to JSONL."""
    if not BENCHMARK_DATA.exists():
        return {}
    result = {}
    raw = BENCHMARK_DATA.read_text(encoding="utf-8").replace("\\n", "\n")
    for line in raw.splitlines():
        try:
            row = json.loads(line)
            result[str(row.get("entry_id"))] = row
        except Exception:
            continue
    try:
        from core.storage import read_reviews
        return read_reviews(lambda: list(result.values()))
    except Exception:
        return result


def write_benchmark_review(row):
    """Persist a benchmark review row (PostgreSQL primary, JSONL backup)."""
    try:
        from core.control_store import enabled as pg_write_enabled, persist_review
        if pg_write_enabled():
            persist_review(row)
            return
    except Exception:
        raise
    BENCHMARK_DATA.parent.mkdir(parents=True, exist_ok=True)
    with _JSONL_LOCK.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            with BENCHMARK_DATA.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + chr(10))
                f.flush()
                os.fsync(f.fileno())
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    try:
        from core.pg_mirror import mirror_review
        mirror_review(row)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Taxonomy feedback helpers
# ---------------------------------------------------------------------------
def read_taxonomy_feedback():
    """Read taxonomy feedback keyed by entry_id, preferring PostgreSQL."""
    if not TAXONOMY_FEEDBACK_DATA.exists():
        return {}
    out = {}
    for line in TAXONOMY_FEEDBACK_DATA.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            out[str(row.get("entry_id"))] = row
        except Exception:
            continue
    try:
        from core.storage import read_taxonomy
        return read_taxonomy(lambda: list(out.values()))
    except Exception:
        return out


def write_taxonomy_feedback_jsonl(feedback):
    """Append a taxonomy feedback row to JSONL (fallback when PostgreSQL write is unavailable)."""
    TAXONOMY_FEEDBACK_DATA.parent.mkdir(parents=True, exist_ok=True)
    with _JSONL_LOCK.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            with TAXONOMY_FEEDBACK_DATA.open("a", encoding="utf-8") as f:
                f.write(json.dumps(feedback, ensure_ascii=False, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    try:
        from core.pg_mirror import mirror_taxonomy
        mirror_taxonomy(feedback)
    except Exception:
        pass


def clean_list(value, limit=8, max_len=40):
    """Normalise a list field: dedup, strip, truncate."""
    if not isinstance(value, list):
        return []
    out = []
    for x in value:
        x = str(x).strip()
        if x and x not in out:
            out.append(x[:max_len])
    return out[:limit]
