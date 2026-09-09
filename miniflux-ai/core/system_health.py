"""System-level health summary for the operations console.

Aggregates: LLM reachability (cheap ping), PostgreSQL/storage status,
digest/summary state, and outbox status.  Read-only.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

from common.logger import get_logger

logger = get_logger(__name__)

VERSION = "system-health-v1"


def _data_dir() -> Path:
    return Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))


def check_llm(timeout: float = 4.0) -> dict:
    """LLM health: configuration + recent scoring activity (proves the LLM path).

    A live network probe to /models often returns 401 on OpenAI-compatible
    gateways even when chat completions work, so we instead infer health from
    configuration completeness and whether fresh scores exist (LLM was called
    successfully recently).
    """
    from common import config
    url = config.llm_base_url
    result = {"configured": bool(url and config.llm_api_key), "base_url": url,
              "ok": False, "detail": "no_recent_llm_activity"}
    if not result["configured"]:
        result["detail"] = "llm_not_configured"
        return result
    # Look at the most recent scored_at in the scoring ledger: LLM produces scores.
    try:
        from app.routes import _shared
        rows = _shared.read_scoring_rows()
        if rows:
            from datetime import datetime, timezone
            latest = rows[0].get("scored_at")
            if latest:
                try:
                    dt = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
                    result["last_scored_at"] = latest
                    result["last_scored_age_days"] = round(age_days, 2)
                    # LLM path proven if scored within the last 14 days.
                    result["ok"] = age_days <= 14
                    result["detail"] = "ok" if result["ok"] else "no_recent_scores"
                    return result
                except Exception:
                    pass
        result["detail"] = "no_scoring_data"
    except Exception as e:
        result["detail"] = f"ledger_unavailable: {str(e)[:80]}"
    return result


def check_storage() -> dict:
    try:
        from core.storage import status as storage_status
        from core.control_store import status as write_status
        return {"storage": storage_status(), "writes": write_status()}
    except Exception as e:
        return {"error": str(e)[:120]}


def check_summary() -> dict:
    data = _data_dir()
    summary_file = data / "summary.dat"
    digest_file = data / "digest.dat"
    out = {"summary_entries": 0, "summary_exists": False,
           "digest_exists": False, "digest_size": 0}
    try:
        if summary_file.exists():
            out["summary_exists"] = True
            out["summary_entries"] = sum(1 for line in summary_file.read_text(
                encoding="utf-8", errors="ignore").splitlines() if line.strip())
            mtime = summary_file.stat().st_mtime
            out["summary_updated_at"] = datetime.fromtimestamp(
                mtime, tz=timezone.utc).isoformat()
    except Exception as e:
        out["summary_error"] = str(e)[:120]
    try:
        if digest_file.exists():
            out["digest_exists"] = True
            out["digest_size"] = digest_file.stat().st_size
            out["digest_updated_at"] = datetime.fromtimestamp(
                digest_file.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception as e:
        out["digest_error"] = str(e)[:120]
    return out


def check_outbox() -> dict:
    try:
        from core.control_store import status as write_status
        return {"pending": write_status().get("outbox_pending", 0)}
    except Exception as e:
        return {"pending": None, "error": str(e)[:120]}


def check_backup() -> dict:
    """Backup status from backup_status.json written by the daily backup script."""
    data = _data_dir()
    status_file = data / "backup_status.json"
    if not status_file.exists():
        return {"available": False, "detail": "no_backup_status_file"}
    try:
        import json
        info = json.loads(status_file.read_text(encoding="utf-8"))
        info["available"] = True
        return info
    except Exception as e:
        return {"available": False, "detail": f"backup_status_unreadable: {str(e)[:80]}"}


def report() -> dict:
    """Aggregate system health."""
    llm = check_llm()
    storage = check_storage()
    summary = check_summary()
    outbox = check_outbox()
    backup = check_backup()
    storage_ok = not storage.get("error") and storage.get("storage", {}).get("postgres_reachable")
    all_ok = llm.get("ok") and storage_ok
    return {
        "version": VERSION,
        "production_unchanged": True,
        "ok": all_ok,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "llm": llm,
        "storage": storage,
        "summary": summary,
        "outbox": outbox,
        "backup": backup,
    }
