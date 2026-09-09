"""V131 article/advice/archive routes extracted from scoring.py; compatibility-safe.

Routes are registered on the shared ``scoring_bp`` Blueprint owned by
``scoring.py``.  Shared data helpers come from ``_shared``.
"""
from flask import jsonify, request

from app.routes import _shared
from app.routes.scoring import scoring_bp
from core.advice_store import record
from core.article_actions import archive_entry
from core.miniflux_client import get_miniflux_client
from core.feed_policy import get_weight, apply_weight


@scoring_bp.get("/api/recommendations")
def recommendations():
    rows = _shared.read_scoring_rows()
    latest = {}
    for r in rows:
        eid = r.get("entry_id")
        if eid is not None and eid not in latest:
            latest[eid] = r
    items = []
    for r in latest.values():
        score = r.get("score")
        if not isinstance(score, (int, float)):
            continue
        fid = r.get("feed_id")
        weight = get_weight(fid) if fid is not None else 100
        base = r.get("base_score", score)
        adjusted = apply_weight(base, fid) if fid is not None else score
        items.append({**r, "base_score": base, "feed_weight": weight, "recommended_score": adjusted})
    items.sort(key=lambda x: (x["recommended_score"], x.get("scored_at", '')), reverse=True)
    return jsonify({"version": "recommendations-v1", "items": items[:30]})


@scoring_bp.get("/api/article-advice")
def article_advice():
    rows = _shared.read_scoring_rows()
    items = [{**r, "type": "archive_suggestion", "requires_approval": True,
              "reason": "AI 评分低于 20，建议归档以减少低价值内容干扰。"}
             for r in rows if isinstance(r.get("score"), int) and r.get("score") < 20]
    return jsonify({"version": "article-advice-v1", "requires_approval": True, "items": items})


@scoring_bp.post("/api/article-advice/<int:entry_id>/action")
def article_advice_action(entry_id):
    rows = {int(r["entry_id"]): r for r in _shared.read_scoring_rows()}
    item = rows.get(entry_id)
    if not item:
        return jsonify({"error": "entry_not_found"}), 404
    if not isinstance(item.get("score"), int) or item["score"] >= 20:
        return jsonify({"error": "entry_not_eligible_for_archive"}), 400
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("approve", "reject"):
        return jsonify({"error": "action_must_be_approve_or_reject"}), 400
    if action == "reject":
        return jsonify(record("article_archive_rejected", item) | {"executed": False})
    try:
        current = get_miniflux_client().get_entry(entry_id)
        previous_status = current.get("status", "unread")
    except Exception:
        previous_status = "unread"
    if previous_status == "read":
        return jsonify({"executed": False, "skipped": True, "reason": "already_read",
                        "previous_status": previous_status,
                        "message": "文章已经是已读状态，无需重复归档。"})
    result = archive_entry(entry_id)
    audit = record("article_archive_approved", item | {"previous_status": previous_status})
    return jsonify(audit | {"executed": True, "miniflux_result": bool(result),
                    "message": "已归档文章。可在最近操作中撤销。", "previous_status": previous_status})


@scoring_bp.get("/api/article-archive/queue")
def article_archive_queue():
    """Return human-reviewed archive marks that are waiting for explicit execution."""
    reviews = _shared.read_benchmark_reviews()
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    items = []
    for eid, review in reviews.items():
        if review.get("status") != "archive":
            continue
        row = rows.get(str(eid), {})
        items.append({"entry_id": int(eid), "title": row.get("title", review.get("title", f"文章 #{eid}")),
                      "score": row.get("score"),
                      "marked_at": review.get("reviewed_at", review.get("at")),
                      "notes": review.get("notes", "")})
    items.sort(key=lambda x: x.get("marked_at") or "", reverse=True)
    return jsonify({"version": "article-archive-queue-v1", "count": len(items), "items": items})


@scoring_bp.post("/api/article-archive/execute")
def article_archive_execute():
    """Execute only explicitly selected, human-marked archive candidates."""
    data = request.get_json(silent=True) or {}
    ids = data.get("entry_ids")
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "entry_ids_required"}), 400
    auto_mark = bool(data.get("auto_mark", False))
    reviews = _shared.read_benchmark_reviews()
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    results = []
    errors = []
    for raw_id in ids:
        try:
            eid = int(raw_id)
        except (TypeError, ValueError):
            errors.append({"entry_id": raw_id, "error": "invalid_entry_id"})
            continue
        review = reviews.get(str(eid), {})
        if review.get("status") != "archive" and not auto_mark:
            errors.append({"entry_id": eid, "error": "not_marked_for_archive"})
            continue
        item = rows.get(str(eid), {"entry_id": eid, "title": review.get("title", f"文章 #{eid}")})
        try:
            current = get_miniflux_client().get_entry(eid)
            previous_status = current.get("status", "unread")
            if previous_status == "read":
                results.append({"entry_id": eid, "title": item.get("title"), "executed": False,
                                "skipped": True, "reason": "already_read", "previous_status": previous_status})
                continue
            result = archive_entry(eid)
            audit = record("article_archive_approved", item | {"previous_status": previous_status,
                                                               "source": "review_archive_queue"})
            # Mark the benchmark review as executed so it leaves the archive review queue.
            try:
                from app.routes import _shared as _s
                import datetime as _dt
                _s.write_benchmark_review({
                    "entry_id": eid,
                    "status": "executed",
                    "category": "归档已执行",
                    "human_score": None,
                    "score_range": None,
                    "notes": "[archived] 已实际执行归档",
                    "reviewed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                    "executed_at": audit.get("at"),
                })
            except Exception:
                pass
            results.append({"entry_id": eid, "title": item.get("title"), "executed": True,
                            "previous_status": previous_status, "audit": audit})
        except Exception as exc:
            errors.append({"entry_id": eid, "error": str(exc)})
    return jsonify({"executed": len(results), "failed": len(errors),
                    "results": results, "errors": errors,
                    "message": f"已执行 {len(results)} 篇归档。" if results else "没有文章被归档。"})


@scoring_bp.get("/api/article-actions/recent")
def article_recent_actions():
    actions = [row for row in _shared.read_actions()
               if row.get("action") in {"article_archive_approved", "article_archive_rollback"}]
    state = {}
    for row in actions:
        eid = str(row.get("advice", {}).get("entry_id"))
        if eid:
            state[eid] = row
    items = []
    for eid, row in sorted(state.items(), key=lambda kv: kv[1].get("at", ""), reverse=True)[:20]:
        if row.get("action") == "article_archive_approved":
            items.append({"entry_id": int(eid), "title": row.get("advice", {}).get("title"),
                          "at": row.get("at"),
                          "previous_status": row.get("advice", {}).get("previous_status", "unread"),
                          "can_undo": True})
    return jsonify({"version": "article-actions-recent-v1", "items": items})


@scoring_bp.post("/api/article-advice/<int:entry_id>/rollback")
def article_advice_rollback(entry_id):
    previous_status = "unread"
    for row in _shared.read_actions():
        if row.get("action") in {"article_archive_approved", "auto_archive_silenced"} and str(row.get("advice", {}).get("entry_id") or row.get("entry_id")) == str(entry_id):
            previous_status = row.get("advice", {}).get("previous_status", "unread")
    client = get_miniflux_client()
    result = client.update_entries([int(entry_id)],
                                   previous_status if previous_status in {"read", "unread"} else "unread")
    return jsonify(record("article_archive_rollback", {"entry_id": entry_id, "restored_status": previous_status})
                   | {"executed": True, "miniflux_result": bool(result),
                      "message": "已撤销归档，文章恢复到归档前状态。", "restored_status": previous_status})


@scoring_bp.post("/api/article-actions/rollback-all")
def article_actions_rollback_all():
    """Batch rollback all recent archive actions."""
    recent_actions = [row for row in _shared.read_actions()
                      if row.get("action") in {"article_archive_approved", "auto_archive_silenced"}]
    client = get_miniflux_client()
    rolled_back = []
    seen = set()
    for row in reversed(recent_actions):
        eid = str(row.get("advice", {}).get("entry_id") or row.get("entry_id") or "")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        try:
            prev = row.get("advice", {}).get("previous_status", "unread")
            client.update_entries([int(eid)], prev if prev in {"read", "unread"} else "unread")
            record("article_archive_rollback", {"entry_id": int(eid), "restored_status": prev})
            rolled_back.append(int(eid))
        except Exception:
            pass
    return jsonify({
        "version": "rollback-all-v1",
        "rolled_back_count": len(rolled_back),
        "entry_ids": rolled_back,
        "message": f"已成功批量撤销 {len(rolled_back)} 篇归档记录，已恢复原始阅读状态。" if rolled_back else "暂无可撤销的归档记录。"
    })


@scoring_bp.get("/api/search")
def article_search():
    """Full-text search across Miniflux entries, enriched with AI scores."""
    q = request.args.get("q", "")
    limit = request.args.get("limit", "20")
    from core.search import search_entries
    return jsonify(search_entries(q, limit))


@scoring_bp.get("/api/recommendations/consistency")
def recommendations_consistency():
    """Read-only ranking consistency check for the recommendation list."""
    from core.recommendation_consistency import check_consistency
    resp = recommendations()
    items = resp.get_json().get("items", [])
    result = check_consistency(items)
    return jsonify({**result, "checked_at_items": len(items)})
