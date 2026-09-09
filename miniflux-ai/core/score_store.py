import hashlib
import json
import os
import threading
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux production path uses fcntl
    fcntl = None

_LOCK = threading.Lock()
_PATH = os.environ.get("AI_WORKER_DATA_DIR", "/app/data") + "/scoring_results.jsonl"


def content_hash(title, content):
    return hashlib.sha256((str(title) + "\n" + str(content)).encode("utf-8")).hexdigest()


def _read_records():
    if not os.path.exists(_PATH):
        return []
    rows = []
    with open(_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Preserve forward progress when an old append was interrupted.
                continue
    return rows


def get_cached(entry_id, content_hash_value):
    try:
        from core.control_store import enabled as pg_write_enabled, cached_scoring
        if pg_write_enabled():
            cached = cached_scoring(entry_id, content_hash_value)
            if cached and cached.get("score") is not None:
                return cached
    except Exception:
        pass
    latest = None
    for r in _read_records():
        if r.get("entry_id") == entry_id and r.get("content_hash") == content_hash_value and r.get("score") is not None:
            latest = r
    return latest


def migrate_entry_hash(entry_id, content_hash_value):
    rows = _read_records()
    changed = False
    candidates = []
    for r in rows:
        if r.get("entry_id") == entry_id and r.get("score") is not None:
            candidates.append(r)
    if not candidates:
        return None
    for r in candidates:
        if not r.get("content_hash"):
            r["content_hash"] = content_hash_value
            changed = True
    if changed:
        with _LOCK:
            tmp = _PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
            os.replace(tmp, _PATH)
    return get_cached(entry_id, content_hash_value)


def save_result(entry_id, title, result, feed_id=None, content_hash_value=None):
    base = result.get("base_score", result.get("score"))
    weight = result.get("feed_weight", 100)
    rec_score = result.get("recommend_score", result.get("score"))
    record = {
        "entry_id": entry_id,
        "feed_id": feed_id,
        "title": title,
        "content_hash": content_hash_value,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "score": rec_score,
        "base_score": base,
        "feed_weight": weight,
        "recommend_score": rec_score,
        "judge": result.get("judge"),
        "reason": result.get("reason"),
        "confidence": result.get("confidence"),
        "attempt": result.get("attempt"),
        "error": result.get("error"),
        "score_version": result.get("score_version", "v20"),
        "calibration": result.get("score_version", "v20"),
    }
    try:
        from core.control_store import enabled as pg_write_enabled, persist_scoring
        if pg_write_enabled():
            persist_scoring(record)
            return record
    except Exception:
        raise
    with _LOCK:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                if fcntl is not None:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    try:
        from core.pg_mirror import mirror_scoring_result
        mirror_scoring_result(record)
    except Exception:
        # JSONL is still authoritative during migration; hourly sync repairs PG.
        pass
    return record
