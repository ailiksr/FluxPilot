"""Automated actions on Miniflux entries for pure native reading (Reactflux/Miniflux).

1. Auto-Starring (High Quality >= 75 or Rule Boosted):
   - Strict idempotency check: only call toggle_bookmark if starred is currently False.
   - Never accidentally un-star an article already bookmarked by the user.

2. Auto-Silencing / Auto-Mark-Read (Rule Muted or Score < 25):
   - Mark as read directly in Miniflux so it disappears from the unread stream in Reactflux.
   - Record audit trail in action_events with previous_status='unread', enabling 100% reversible undo.

3. Visual Score Badge:
   - Prepended to AI summary in HTML, letting users immediately see the score in Reactflux.
"""
from __future__ import annotations

from typing import Any
from common.logger import get_logger
from core.miniflux_client import get_miniflux_client

logger = get_logger(__name__)


def auto_star_entry(entry_id: int, score: float | int | None, is_boosted: bool = False, entry_dict: dict[str, Any] | None = None) -> bool:
    """Idempotently star high-quality or boosted entries in Miniflux.
    
    Returns True if newly starred, False otherwise.
    """
    if score is None and not is_boosted:
        return False
    
    score_val = float(score) if score is not None else 0.0
    if score_val < 75.0 and not is_boosted:
        return False

    try:
        client = get_miniflux_client()
        # Idempotency safety: verify current starred status
        starred = None
        if entry_dict and "starred" in entry_dict:
            starred = bool(entry_dict["starred"])
        else:
            mf_entry = client.get_entry(entry_id)
            starred = bool(mf_entry.get("starred", False))

        if starred:
            logger.debug(f"Entry #{entry_id} is already starred; skipping toggle.")
            return False

        # Toggle to star
        client.toggle_bookmark(entry_id)
        logger.info(f"⭐ Entry #{entry_id} auto-starred in Miniflux (score={score_val}, boosted={is_boosted})")
        return True
    except Exception as e:
        logger.warning(f"Failed to auto-star entry #{entry_id}: {e}")
        return False


def auto_silence_entry(entry_id: int, score: float | int | None, is_muted: bool = False, mute_reasons: list[str] | None = None, entry_dict: dict[str, Any] | None = None) -> bool:
    """Auto-mark low-quality or muted entries as read in Miniflux with full audit trail."""
    score_val = float(score) if score is not None else 50.0
    
    # Must be rule-muted OR strongly low-quality (< 25)
    if not is_muted and score_val >= 25.0:
        return False

    try:
        client = get_miniflux_client()
        current_status = None
        title = ""
        if entry_dict:
            current_status = entry_dict.get("status")
            title = entry_dict.get("title") or f"文章 #{entry_id}"
        if not current_status:
            mf_entry = client.get_entry(entry_id)
            current_status = mf_entry.get("status", "unread")
            title = mf_entry.get("title") or title

        if current_status == "read":
            logger.debug(f"Entry #{entry_id} is already read; skipping silence.")
            return False

        # Update in Miniflux to 'read'
        client.update_entries([entry_id], "read")

        # Record reversible audit trail in action_events
        from core.advice_store import record
        reasons_text = "；".join(mute_reasons) if mute_reasons else f"AI 质量分极低 ({score_val:.0f}/100)"
        record("auto_archive_silenced", {
            "entry_id": entry_id,
            "title": title,
            "previous_status": "unread",
            "reason": reasons_text,
            "score": score_val,
            "is_muted": is_muted
        })
        logger.info(f"🗑️ Entry #{entry_id} auto-silenced as read in Miniflux: {reasons_text}")
        return True
    except Exception as e:
        logger.warning(f"Failed to auto-silence entry #{entry_id}: {e}")
        return False


def build_score_badge(score: float | int | None, label: str | None = None) -> str:
    """Generate clean HTML badge for embedding directly in the article summary."""
    if score is None:
        return ""
    sc = int(round(float(score)))
    if sc >= 80:
        bg, fg, tag = "#ecfdf3", "#067647", "⭐ 优先精选"
    elif sc >= 65:
        bg, fg, tag = "#eff8ff", "#175cd3", "值得一读"
    elif sc < 30:
        bg, fg, tag = "#fff1f0", "#b42318", "垃圾水文"
    else:
        bg, fg, tag = "#fffaeb", "#b54708", "普通资讯"

    desc = label or tag
    return (
        f'<div class="rss-ai-badge" style="display:inline-block;padding:3px 9px;margin-bottom:8px;'
        f'border-radius:6px;background:{bg};color:{fg};font-size:12px;font-weight:700;'
        f'border:1px solid rgba(0,0,0,0.06);">'
        f'🤖 AI 评分 {sc}/100 · {desc}'
        f'</div>'
    )


def build_decision_inspector(
    scoring: dict[str, Any] | None = None,
    rule_match: dict[str, Any] | None = None,
    pipeline_trace: dict[str, Any] | None = None,
    entry_id: int | None = None,
) -> str:
    """Generate an interactive, collapsible AI Decision Inspector card (Native HTML).

    Renders natively in Reactflux, Miniflux, and any RSS reader using standard
    <details> and <summary> tags with inline styling.
    Provides complete transparency into why an article was scored, boosted, or silenced.
    """
    if not scoring:
        return ""

    score_val = scoring.get("score")
    if score_val is None:
        return ""

    sc = int(round(float(score_val)))
    if sc >= 80:
        bg, fg, tag = "#ecfdf3", "#067647", "⭐ 优先精选"
    elif sc >= 65:
        bg, fg, tag = "#eff8ff", "#175cd3", "值得一读"
    elif sc < 30:
        bg, fg, tag = "#fff1f0", "#b42318", "垃圾水文"
    else:
        bg, fg, tag = "#fffaeb", "#b54708", "普通资讯"

    judge = scoring.get("judge") or {}
    tax = judge.get("taxonomy") or scoring.get("taxonomy") or {}
    topics = tax.get("topics") or []
    kws = tax.get("matched_keywords") or []

    # Path & Stage description
    is_fast_path = scoring.get("fast_path") or (pipeline_trace and pipeline_trace.get("fast_path"))
    if is_fast_path:
        stage_desc = "⚡ 前置规则启发式快速熔断 (耗时<1ms，跳过LLM)"
    elif scoring.get("cached"):
        stage_desc = "⚡ 评分结构缓存命中 (复用已有 Judge 分析)"
    else:
        stage_desc = "🤖 大模型六维连续评分深度研判 (V23)"

    rule_notes = []
    if rule_match:
        if rule_match.get("boosted"):
            rule_notes.append('<span style="color:#067647;font-weight:700">🟢 规则加权提权 (+15分)</span>')
        if rule_match.get("demoted"):
            rule_notes.append('<span style="color:#b54708;font-weight:700">🟡 轻度降权惩罚 (-15分)</span>')
        if rule_match.get("muted"):
            rule_notes.append('<span style="color:#b42318;font-weight:700">🔴 规则命中静音沉底</span>')

    rule_path_str = f"{stage_desc} {' ➔ ' + '、'.join(rule_notes) if rule_notes else ''}"

    # Matched terms
    matched_parts = []
    if topics:
        matched_parts.append(f"主题: {', '.join(str(t) for t in topics[:4])}")
    if kws:
        matched_parts.append(f"命中词: {', '.join(str(k) for k in kws[:5])}")
    matched_str = " · ".join(matched_parts) if matched_parts else "常规资讯流"

    # Multi-dimensional score summary
    info = judge.get("information", "—")
    depth = judge.get("depth", "—")
    orig = judge.get("originality", "—")
    promo = judge.get("promotional", "—")
    dims_str = f"信息量: {info}/5 │ 深度: {depth}/5 │ 原创: {orig}/5 │ 营销度: {promo}/5"

    reason_str = scoring.get("reason") or "综合评估内容质量、主题相关性与营销信号"

    eid_text = f"文章 #{entry_id} · " if entry_id else ""
    import os
    lan_ip = os.environ.get("LAN_IP") or os.environ.get("HOST_IP") or "127.0.0.1"
    port_ai = os.environ.get("PORT_AI_CONSOLE", "18090")
    console_link = f"http://{lan_ip}:{port_ai}/ai-worker#rules"

    return (
        f'<details class="rss-ai-inspector" style="margin-bottom:12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;font-size:12px;color:#334155;line-height:1.6;">'
        f'<summary style="cursor:pointer;font-weight:700;display:flex;align-items:center;justify-content:space-between;list-style:none;outline:none;">'
        f'<span><span style="display:inline-block;padding:2px 8px;border-radius:6px;background:{bg};color:{fg};font-weight:800;font-size:11px;margin-right:6px;">🤖 AI 评分 {sc}/100</span><span style="color:#475467;">{tag}</span></span>'
        f'<span style="color:#0284c7;font-size:11px;font-weight:600;">研判依据与溯源 ▾</span>'
        f'</summary>'
        f'<div style="margin-top:8px;padding-top:8px;border-top:1px dashed #cbd5e1;font-size:11px;display:grid;gap:4px;">'
        f'<div><b>🛣️ 研判路径：</b>{rule_path_str}</div>'
        f'<div><b>🏷️ 命中偏好：</b>{matched_str}</div>'
        f'<div><b>📊 多维量化：</b>{dims_str}</div>'
        f'<div><b>💡 研判依据：</b>{reason_str}</div>'
        f'<div style="margin-top:4px;display:flex;justify-content:space-between;align-items:center;color:#64748b;font-size:10px;">'
        f'<span>{eid_text}规则可信溯源</span>'
        f'<a href="{console_link}" target="_blank" style="color:#0284c7;text-decoration:none;font-weight:600;">⚙️ 规则快捷管理 ↗</a>'
        f'</div>'
        f'</div>'
        f'</details>'
    )
