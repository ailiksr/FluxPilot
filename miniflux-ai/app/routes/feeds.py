"""V131 feeds routes extracted from scoring.py; compatibility-safe.

Routes are registered on the shared ``scoring_bp`` Blueprint owned by
``scoring.py``.  Shared data helpers come from ``_shared``.
"""
from flask import jsonify, request

from app.routes import _shared
from app.routes.scoring import scoring_bp
from core.feed_advisor import build_advice
from core.advice_store import record
from core.feed_policy import set_weight, rollback, get_weight, load as load_weights


@scoring_bp.get("/api/feed-policy")
def feed_policy_list():
    """Read-only overview of all known Feeds: AI weight, quality and health.

    Only the AI Worker's local recommendation weight is shown; Miniflux feed
    configuration is never modified here.
    """
    rows = _shared.read_scoring_rows()
    from collections import defaultdict
    by_feed = defaultdict(list)
    for r in rows:
        fid = r.get("feed_id")
        if fid is not None:
            by_feed[str(fid)].append(r)
    weights = load_weights()
    try:
        from core.feed_health import report as health_report, trends as health_trends
        health = {str(x.get("feed_id")): x for x in health_report()}
        trends_map = {str(x.get("feed_id")): x for x in health_trends(hours=24).get("feeds", [])}
    except Exception:
        health = {}
        trends_map = {}

    try:
        from core.feed_quality_v2 import build_quality_report
        quality_map = {str(x.get("feed_id")): x for x in build_quality_report(rows)}
    except Exception:
        quality_map = {}

    # Merge read-only Miniflux feed metadata (URL, interval, disabled state).
    miniflux_feeds = {}
    try:
        from core.miniflux_client import get_miniflux_client
        mf = get_miniflux_client().get_feeds() or []
        for f in mf:
            miniflux_feeds[str(f.get("id"))] = f
    except Exception:
        miniflux_feeds = {}

    all_feed_ids = sorted(
        set(list(by_feed.keys()) + list(miniflux_feeds.keys())),
        key=lambda x: (int(x) if x.isdigit() else 9999, x)
    )

    items = []
    for fid in all_feed_ids:
        fr = by_feed.get(fid, [])
        scored = [x for x in fr if isinstance(x.get("score"), (int, float))]
        avg = round(sum(x["score"] for x in scored) / len(scored), 1) if scored else None
        low_rate = round(sum(1 for x in scored if x["score"] < 25) / len(scored), 3) if scored else 0.0
        high_rate = round(sum(1 for x in scored if x["score"] >= 80) / len(scored), 3) if scored else 0.0
        w = weights.get(str(fid), {})
        h = health.get(str(fid), {})
        tr = trends_map.get(str(fid), {})
        q = quality_map.get(str(fid), {})
        mf = miniflux_feeds.get(str(fid), {})
        items.append({
            "feed_id": fid,
            "title": h.get("title") or (fr[-1].get("feed_title") if fr else "") or (fr[-1].get("feed_name") if fr else "") or mf.get("title") or f"Feed #{fid}",
            "feed_url": mf.get("feed_url"),
            "site_url": mf.get("site_url"),
            "disabled": mf.get("disabled", False),
            "next_check_at": mf.get("next_check_at"),
            "checked_at": mf.get("checked_at"),
            "parsing_error": mf.get("parsing_error_message"),
            "weight": int(w.get("weight", 100)),
            "previous_weight": w.get("previous_weight"),
            "weight_reason": w.get("reason"),
            "weight_updated_at": w.get("updated_at"),
            "average_score": avg,
            "low_rate": low_rate,
            "high_rate": high_rate,
            "sample_size": len(scored),
            "health_action": h.get("action", "healthy"),
            "health_label": h.get("label", "抓取正常"),
            "success_rate": h.get("success_rate", 1.0),
            "average_latency_ms": tr.get("average_latency_ms") or h.get("average_latency_ms"),
            "p95_latency_ms": tr.get("p95_latency_ms") or h.get("p95_latency_ms"),
            "consecutive_failures": h.get("consecutive_failures", 0),
            "series": tr.get("series", []),
            "quality_action": q.get("action", "maintain"),
            "quality_label": q.get("label", "保持当前优先级"),
            "quality_reasons": q.get("reasons", []),
            "quality_confidence": q.get("confidence", 0.8),
            "production_unchanged": True,
        })
    items.sort(key=lambda x: (int(x["feed_id"]) if str(x["feed_id"]).isdigit() else 9999))
    return jsonify({"version": "feed-policy-list-v1", "production_unchanged": True,
                    "count": len(items), "items": items})


@scoring_bp.post("/api/feed-policy/<int:feed_id>/weight")
def feed_policy_set_weight(feed_id):
    """Manually adjust a Feed's AI recommendation weight (0-100).

    Only affects the AI Worker's local recommendation ranking; Miniflux feed
    configuration is never modified.  Previous weight is preserved for rollback.
    """
    data = request.get_json(silent=True) or {}
    raw = data.get("weight")
    if raw is None:
        return jsonify({"error": "weight_required"}), 400
    try:
        weight = int(raw)
    except (TypeError, ValueError):
        return jsonify({"error": "weight_must_be_integer"}), 400
    if not 0 <= weight <= 100:
        return jsonify({"error": "weight_out_of_range_0_100"}), 400
    reason = str(data.get("reason") or "人工调整 AI 推荐权重").strip()[:200]
    policy = set_weight(feed_id, weight, reason)
    record("feed_weight_manual", {"feed_id": feed_id, "policy": policy})
    return jsonify({"version": "feed-policy-set-v1", "executed": True,
                    "feed_id": feed_id, "policy": policy,
                    "message": "已调整 AI 推荐权重，未修改 Miniflux Feed 配置。"})


@scoring_bp.get("/api/feed-advice")
def feed_advice():
    from core.feed_quality_v2 import build_quality_report
    rows = _shared.read_scoring_rows()
    items = build_quality_report(rows)
    try:
        from core.feed_health import report as health_report
        health = {str(x.get("feed_id")): x for x in health_report()}
        for item in items:
            item["health"] = health.get(str(item.get("feed_id")))
    except Exception:
        pass
    return jsonify({"requires_approval": True, "version": "feed-quality-v2", "items": items})


@scoring_bp.post("/api/feed-advice/<int:index>/action")
def feed_advice_action(index):
    rows = _shared.read_scoring_rows()
    items = build_advice(rows)
    if index < 0 or index >= len(items):
        return jsonify({"error": "advice_not_found"}), 404
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("approve", "reject"):
        return jsonify({"error": "action_must_be_approve_or_reject"}), 400
    item = items[index]
    if action == "approve":
        new_weight = 50 if item.get('type') == 'deprioritize' else 75
        policy = set_weight(item['feed_id'], new_weight, item['reason'])
        return jsonify(record("approved_executed", item) | {"executed": True, "policy": policy,
                        "message": "已批准：仅调整 AI Worker 本地权重，未修改 Miniflux Feed。"})
    return jsonify(record("rejected", item) | {"executed": False, "message": "已拒绝该建议。"})


@scoring_bp.post("/api/feed-policy/<int:feed_id>/rollback")
def feed_policy_rollback(feed_id):
    policy = rollback(feed_id)
    if policy is None:
        return jsonify({"error": "policy_not_found"}), 404
    record("rollback", {"feed_id": feed_id, "policy": policy})
    return jsonify({"executed": True, "policy": policy})


@scoring_bp.get("/api/feed-health/heal-logs")
def feed_heal_logs():
    """Read recent self-healing actions and logs."""
    from core.feed_healer import _read_heal_logs
    logs = _read_heal_logs(50)
    return jsonify({"version": "feed-healer-logs-v1", "count": len(logs), "logs": logs})


@scoring_bp.post("/api/feed-health/heal-now")
def feed_heal_now():
    """Immediately run auto-diagnosis and graduated self-healing on all feeds."""
    from core.feed_healer import heal_all_feeds
    result = heal_all_feeds()
    return jsonify(result)
