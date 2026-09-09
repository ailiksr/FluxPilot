"""Self-Healing RSS Feed Engine (Auto-Diagnose & Auto-Recover).

Reference: FreshRSS Auto-Repair, Inoreader Broken Feed Detector.

Detects network timeouts, HTTP 403 blocks, protocol deadlocks, and accidental
Miniflux disabled states, then applies graduated healing steps:
  Step 1: Un-disable & re-activate feeds if network is responsive.
  Step 2: Disable HTTP/2 (force HTTP/1.1) for timeouts & TLS deadline errors.
  Step 3: Inject Chrome Desktop User-Agent for 403 / anti-bot blocks.
  Step 4: Auto-discover alternative feed URLs for 404 / broken paths.
  Step 5: Circuit Breaker: Max 3 heal attempts per feed per 24 hours.

All actions are audited in data/feed_healer_logs.jsonl and visible in the console.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from common.logger import get_logger
from core.miniflux_client import get_miniflux_client

logger = get_logger(__name__)

DATA_DIR = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))
HEAL_LOG_FILE = DATA_DIR / "feed_healer_logs.jsonl"
CIRCUIT_BREAKER_HOURS = 24
MAX_HEAL_ATTEMPTS = 3

CHROME_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def _read_heal_logs(limit: int = 50) -> list[dict[str, Any]]:
    if not HEAL_LOG_FILE.exists():
        return []
    rows = []
    for line in HEAL_LOG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return sorted(rows, key=lambda x: str(x.get("healed_at") or ""), reverse=True)[:limit]


def _record_heal(feed_id: int, action: str, details: str, success: bool = True) -> dict[str, Any]:
    row = {
        "feed_id": feed_id,
        "action": action,
        "details": details,
        "success": success,
        "healed_at": datetime.now(timezone.utc).isoformat(),
    }
    HEAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HEAL_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _can_heal(feed_id: int, recent_logs: list[dict[str, Any]]) -> bool:
    """Circuit breaker: max 3 attempts per feed in the last 24h."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=CIRCUIT_BREAKER_HOURS)
    attempts = 0
    for l in recent_logs:
        if l.get("feed_id") == feed_id:
            try:
                dt = datetime.fromisoformat(l.get("healed_at", "").replace("Z", "+00:00"))
                if dt >= cutoff:
                    attempts += 1
            except Exception:
                pass
    return attempts < MAX_HEAL_ATTEMPTS


def heal_feed(feed: dict[str, Any], recent_logs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Diagnose and auto-heal a single feed based on error signatures."""
    feed_id = int(feed.get("id"))
    title = feed.get("title") or f"Feed #{feed_id}"
    error_cnt = feed.get("parsing_error_count", 0)
    error_msg = str(feed.get("parsing_error_message") or "").strip()
    disabled = bool(feed.get("disabled", False))
    disable_h2 = bool(feed.get("disable_http2", False))
    ua = str(feed.get("user_agent") or "").strip()
    feed_url = str(feed.get("feed_url") or "")
    site_url = str(feed.get("site_url") or "")

    if recent_logs is None:
        recent_logs = _read_heal_logs(100)

    # If completely healthy, no action needed
    if error_cnt == 0 and not disabled and not error_msg:
        return {"feed_id": feed_id, "status": "healthy", "action": "none", "details": "订阅源状态健康，无需自愈"}

    # Check circuit breaker
    if not _can_heal(feed_id, recent_logs):
        return {
            "feed_id": feed_id,
            "status": "tripped",
            "action": "circuit_breaker",
            "details": f"24小时内已自愈达 {MAX_HEAL_ATTEMPTS} 次上限，熔断保护中，避免频繁修改源配置"
        }

    client = get_miniflux_client()
    healed_steps = []
    updates: dict[str, Any] = {}

    # Step 1: Feed was suspended (disabled: True) by Miniflux due to consecutive errors
    if disabled:
        updates["disabled"] = False
        healed_steps.append("解除 Miniflux 自动挂起禁用")

    # Step 2: Timeout / Connection / HTTP/2 protocol handshake deadlock
    err_low = error_msg.lower()
    if any(k in err_low for k in ("timeout", "deadline exceeded", "protocol error", "connection reset", "tls")):
        if not disable_h2:
            updates["disable_http2"] = True
            healed_steps.append("协议降级：关闭 HTTP/2 强制 HTTP/1.1")

    # Step 3: Anti-scraping / 403 Forbidden / Cloudflare Bot block
    if any(k in err_low for k in ("403", "forbidden", "cloudflare", "bot", "access restricted", "user-agent")):
        if not ua or "Mozilla" not in ua:
            updates["user_agent"] = CHROME_DESKTOP_UA
            healed_steps.append("UA 仿真：注入 Chrome 桌面端真实浏览器 User-Agent")

    # Step 4: 404 Not Found / Broken URL - attempt auto-discovery
    if any(k in err_low for k in ("404", "not found", "no such")) and site_url:
        try:
            discovered = client.discover(site_url)
            if discovered and isinstance(discovered, list):
                new_url = discovered[0].get("url")
                if new_url and new_url != feed_url:
                    updates["feed_url"] = new_url
                    healed_steps.append(f"智能重定向：自动嗅探到新地址 {new_url}")
        except Exception as disc_err:
            logger.debug(f"Feed discovery failed for {site_url}: {disc_err}")

    # Apply updates if any step triggered
    if updates:
        try:
            client.update_feed(feed_id, **updates)
            # Trigger immediate refresh test
            time.sleep(0.5)
            client.refresh_feed(feed_id)
            details_str = "；".join(healed_steps)
            _record_heal(feed_id, "auto_heal", details_str, success=True)
            logger.info(f"🩺 Feed #{feed_id} ({title}) 自动自愈修复成功: {details_str}")
            return {
                "feed_id": feed_id,
                "title": title,
                "status": "healed",
                "action": "applied",
                "details": details_str,
                "updates": updates,
            }
        except Exception as apply_err:
            fail_str = f"应用自愈配置失败: {apply_err}"
            _record_heal(feed_id, "heal_failed", fail_str, success=False)
            return {
                "feed_id": feed_id,
                "title": title,
                "status": "error",
                "action": "failed",
                "details": fail_str,
            }

    # If error exists but no heuristics matched, trigger safe retry
    if error_cnt > 0:
        try:
            client.refresh_feed(feed_id)
            return {"feed_id": feed_id, "status": "refreshed", "action": "refresh", "details": f"触发网络重试刷新: {error_msg[:60]}"}
        except Exception as e:
            return {"feed_id": feed_id, "status": "error", "action": "none", "details": str(e)}

    return {"feed_id": feed_id, "status": "no_action", "action": "none", "details": "无需修改配置"}


def heal_all_feeds() -> dict[str, Any]:
    """Diagnose and heal all feeds currently registered in Miniflux."""
    client = get_miniflux_client()
    feeds = client.get_feeds() or []
    recent_logs = _read_heal_logs(100)
    results = []
    healed_count = 0

    for f in feeds:
        res = heal_feed(f, recent_logs)
        results.append(res)
        if res.get("status") == "healed":
            healed_count += 1

    return {
        "version": "feed-healer-v1",
        "checked_feeds": len(feeds),
        "healed_feeds": healed_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
