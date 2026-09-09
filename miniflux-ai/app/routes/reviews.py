"""V131 reviews routes extracted from scoring.py; compatibility-safe.

Routes are registered on the shared ``scoring_bp`` Blueprint owned by
``scoring.py`` so there is exactly one registration surface and URL
ordering stays stable.  Shared data helpers come from ``_shared``.
"""
import json
import os
from pathlib import Path

from flask import jsonify, request

from app.routes import _shared
from app.routes.scoring import scoring_bp
from core.triage import triage_for
from core.taxonomy import taxonomy_status

_DATA_DIR = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))


@scoring_bp.get("/api/benchmark/pending")
def benchmark_pending():
    reviews = _shared.read_benchmark_reviews()
    items = []
    for row in _shared.read_scoring_rows():
        eid = str(row.get("entry_id"))
        review = reviews.get(eid, {"status": "pending"})
        from core.pre_review import DONE_STATUSES as _DONE_ST
        if review.get("status") not in _DONE_ST:
            from core.autonomous_policy import decide as autonomous_decide
            fq = _shared.feed_quality_map()
            items.append({**row, "triage": triage_for(row),
                          "taxonomy_status": taxonomy_status(row.get("judge")),
                          "autonomous": autonomous_decide(row, fq.get(str(row.get("feed_id")), 50)),
                          "human_review": review})
    return jsonify({"version": "benchmark-pending-v1", "count": len(items), "items": items})


@scoring_bp.get("/api/benchmark/reviewed")
def benchmark_reviewed():
    reviews = _shared.read_benchmark_reviews()
    by_id = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    items = []
    for eid, review in reviews.items():
        if review.get("status") in {"keep", "archive", "ignore"}:
            item = dict(by_id.get(eid, {"entry_id": int(eid) if eid.isdigit() else eid}))
            item["triage"] = triage_for(item)
            item["human_review"] = review
            items.append(item)
    return jsonify({"version": "benchmark-reviewed-v1", "count": len(items), "items": items})


@scoring_bp.get("/api/benchmark/metrics")
def benchmark_metrics():
    reviews = _shared.read_benchmark_reviews()
    counts = {"pending": 0, "keep": 0, "archive": 0, "ignore": 0}
    deltas = []
    by_id = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    for eid, review in reviews.items():
        status = review.get("status")
        if status in counts:
            counts[status] += 1
        human = review.get("human_score")
        row = by_id.get(eid)
        ai = row.get("score") if row else None
        if isinstance(ai, (int, float)) and isinstance(human, (int, float)):
            deltas.append(float(human) - float(ai))
    reviewed = sum(counts[k] for k in ("keep", "archive", "ignore"))
    by_decision = {"keep": [], "archive": [], "ignore": []}
    for eid, review in reviews.items():
        status = review.get("status")
        row = by_id.get(eid)
        if status in by_decision and row:
            by_decision[status].append(row.get("score"))
    decision_avg = {k: round(sum(v) / len(v), 1) if v else None for k, v in by_decision.items()}
    return jsonify({"version": "benchmark-metrics-v1", "counts": counts, "reviewed": reviewed,
                    "mean_score_delta": round(sum(deltas) / len(deltas), 2) if deltas else None,
                    "decision_avg_ai_score": decision_avg})


@scoring_bp.get("/api/scoring/feedback-loop")
def scoring_feedback_loop():
    """Read-only V103 report on AI recommendation acceptance and human overrides."""
    from collections import Counter, defaultdict
    reviews = _shared.read_benchmark_reviews()
    accepted = 0
    overridden = 0
    assisted = 0
    by_rec = defaultdict(lambda: {"accepted": 0, "overridden": 0, "total": 0})
    reason_counts = Counter()
    confidence_buckets = defaultdict(lambda: {"accepted": 0, "overridden": 0, "total": 0})
    for review in reviews.values():
        rec = review.get("ai_recommendation")
        if not rec:
            continue
        category = str(review.get("category") or "")
        notes = str(review.get("notes") or "")
        is_accept = category == "接受AI建议" or notes.startswith("[ai_accept]")
        is_override = category == "修改AI建议" or notes.startswith("[ai_override]")
        if not (is_accept or is_override):
            continue
        assisted += 1
        bucket = "<75%"
        try:
            conf = float(review.get("ai_confidence") or 0) * 100
            bucket = "75–84%" if conf < 85 else "85–94%" if conf < 95 else "95%+"
        except Exception:
            pass
        by_rec[str(rec)]["total"] += 1
        confidence_buckets[bucket]["total"] += 1
        if is_accept:
            accepted += 1
            by_rec[str(rec)]["accepted"] += 1
            confidence_buckets[bucket]["accepted"] += 1
        if is_override:
            overridden += 1
            by_rec[str(rec)]["overridden"] += 1
            confidence_buckets[bucket]["overridden"] += 1
            import re
            m = re.search(r"\[feedback:([^\]]+)\]", notes)
            if m:
                for code in m.group(1).split(','):
                    code = code.strip()
                    if code:
                        reason_counts[code] += 1
    decided = accepted + overridden

    def rates(d):
        total = d.get("total", 0)
        return {**d,
                "acceptance_rate": round(d.get("accepted", 0) / total * 100, 1) if total else None,
                "override_rate": round(d.get("overridden", 0) / total * 100, 1) if total else None}
    return jsonify({"version": "feedback-loop-v1", "production_unchanged": True,
                    "assisted": assisted, "decided": decided,
                    "accepted": accepted, "overridden": overridden,
                    "acceptance_rate": round(accepted / decided * 100, 1) if decided else None,
                    "override_rate": round(overridden / decided * 100, 1) if decided else None,
                    "by_recommendation": {k: rates(v) for k, v in by_rec.items()},
                    "by_confidence": {k: rates(v) for k, v in confidence_buckets.items()},
                    "override_reasons": [{"reason": k, "count": v} for k, v in reason_counts.most_common()],
                    "learning_status": "insufficient_sample" if decided < 20 else "ready_for_review"})


@scoring_bp.get("/api/benchmark/calibration")
def benchmark_calibration():
    """Calibration diagnostics only; requires enough real human reviews before acting."""
    reviews = list(_shared.read_benchmark_reviews().values())
    epoch_file = _DATA_DIR / "benchmark_review_epoch.json"
    epoch = {}
    if epoch_file.exists():
        try:
            epoch = json.loads(epoch_file.read_text(encoding="utf-8"))
        except Exception:
            epoch = {}
    ai_by_id = {str(r.get("entry_id")): r.get("score") for r in _shared.read_scoring_rows()}
    reviewed = []
    for r in reviews:
        if r.get("status") not in {"keep", "archive", "ignore"}:
            continue
        human = r.get("human_score")
        ai = r.get("ai_score", ai_by_id.get(str(r.get("entry_id"))))
        if isinstance(human, (int, float)) and isinstance(ai, (int, float)):
            reviewed.append({**r, "ai_score": ai})
    n = len(reviewed)
    decision_count = sum(1 for r in reviews if r.get("status") in {"keep", "archive", "ignore"})
    score_pending = max(0, 20 - n)
    if not n:
        return jsonify({"version": "benchmark-calibration-v1", "ready": False, "reviewed": 0, "historical_decisions": decision_count,
                        "needed": score_pending, "epoch": epoch.get("version", "review-epoch-v1"),
                        "message": "尚无当前评分架构的有效人工评分；历史人工决策仍单独保留，不参与评分校准"})
    deltas = [float(r["human_score"]) - float(r["ai_score"]) for r in reviewed]
    abs_deltas = [abs(x) for x in deltas]
    mean = sum(deltas) / n
    mae = sum(abs_deltas) / n
    ready = n >= 20
    suggested_offset = round(max(-10, min(10, mean)), 1) if ready else None
    return jsonify({"version": "benchmark-calibration-v1", "ready": ready, "reviewed": n, "historical_decisions": decision_count,
                    "needed": score_pending, "mean_delta": round(mean, 2), "mae": round(mae, 2),
                    "suggested_offset": suggested_offset, "epoch": epoch.get("version", "review-epoch-v1"),
                    "message": "达到20条新架构人工样本，可进入校准评估；当前仍不会自动修改评分模型" if ready
                    else "继续积累新架构人工样本；当前仅统计，不修改评分模型"})


@scoring_bp.post("/api/benchmark/<int:entry_id>/review")
def benchmark_review(entry_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status") or data.get("decision")
    if status not in {"keep", "archive", "ignore"}:
        return jsonify({"error": "status_must_be_keep_archive_or_ignore"}), 400
    human_score = data.get("human_score")
    if human_score is not None:
        try:
            human_score = max(0, min(100, int(human_score)))
        except (TypeError, ValueError):
            return jsonify({"error": "human_score_must_be_integer_0_to_100"}), 400
    import datetime
    row = {
        "entry_id": entry_id,
        "status": status,
        "category": data.get("category"),
        "human_score": human_score,
        "score_range": data.get("score_range"),
        "notes": data.get("notes"),
        "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _shared.write_benchmark_review(row)
    return jsonify({"saved": True, "review": row, "executed": False})


@scoring_bp.post("/api/benchmark/<int:entry_id>/undo")
def benchmark_undo(entry_id):
    """Undo a benchmark decision and return the article to the human review inbox.

    If the decision also corresponded to a real Miniflux archive, restore the
    pre-archive state.
    """
    from core.miniflux_client import get_miniflux_client
    current = _shared.read_benchmark_reviews().get(str(entry_id))
    if not current or current.get("status") not in {"keep", "archive", "ignore"}:
        return jsonify({"error": "no_active_review_to_undo"}), 404
    restored_status = None
    actual_archive = False
    state = None
    for row in _shared.read_actions():
        if str(row.get("advice", {}).get("entry_id")) != str(entry_id):
            continue
        if row.get("action") == "article_archive_approved":
            state = row
        elif row.get("action") == "article_archive_rollback":
            state = None
    actual_archive = state is not None
    if actual_archive:
        restored_status = state.get("advice", {}).get("previous_status", "unread")
        client = get_miniflux_client()
        client.update_entries([int(entry_id)], restored_status if restored_status in {"read", "unread"} else "unread")
    import datetime
    _shared.write_benchmark_review({"entry_id": entry_id, "status": "pending", "category": None,
                                     "human_score": None, "score_range": None,
                                     "notes": "撤销上一条人工审核", "undo_of": current,
                                     "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return jsonify({"saved": True, "executed": actual_archive, "restored_status": restored_status,
                    "message": "已撤销人工审核，文章重新回到待审核队列。" if not actual_archive
                    else "已撤销人工审核并恢复文章原状态。"})


@scoring_bp.post("/api/benchmark/<int:entry_id>/taxonomy-feedback")
def taxonomy_feedback(entry_id):
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    row = rows.get(str(entry_id))
    if not row:
        return jsonify({"error": "entry_not_found"}), 404
    data = request.get_json(silent=True) or {}
    taxonomy = data.get("taxonomy") or {}
    if not isinstance(taxonomy, dict):
        return jsonify({"error": "taxonomy_must_be_object"}), 400
    topics = _shared.clean_list(taxonomy.get("topics"), 8, 40)
    keywords = _shared.clean_list(taxonomy.get("keywords", taxonomy.get("matched_keywords")), 8, 60)
    content_type = str(taxonomy.get("content_type", "")).strip()[:40]
    allowed = {"news", "analysis", "tutorial", "review", "opinion", "announcement", "deal", "entertainment", "other"}
    if content_type and content_type not in allowed:
        return jsonify({"error": "invalid_content_type"}), 400
    import datetime
    feedback = {"entry_id": entry_id,
                "taxonomy": {"content_type": content_type, "topics": topics, "matched_keywords": keywords},
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        from core.control_store import enabled as pg_write_enabled, persist_taxonomy
        if pg_write_enabled():
            persist_taxonomy(feedback)
            return jsonify({"saved": True, "entry_id": entry_id, "taxonomy": feedback["taxonomy"],
                            "message": "标签和关键词偏好已保存。"})
    except Exception:
        raise
    _shared.write_taxonomy_feedback_jsonl(feedback)
    return jsonify({"saved": True, "entry_id": entry_id, "taxonomy": feedback["taxonomy"],
                    "message": "标签和关键词偏好已保存。"})


@scoring_bp.get("/api/benchmark/<int:entry_id>/detail")
def benchmark_detail(entry_id):
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    row = rows.get(str(entry_id))
    if not row:
        return jsonify({"error": "entry_not_found"}), 404
    base_taxonomy = (row.get("judge", {}) or {}).get("taxonomy") or row.get("taxonomy") or {}
    override = _shared.read_taxonomy_feedback().get(str(entry_id), {}).get("taxonomy") or {}
    taxonomy = {**base_taxonomy, **override,
                "topics": override.get("topics", base_taxonomy.get("topics", [])),
                "matched_keywords": override.get("matched_keywords", base_taxonomy.get("matched_keywords", []))}
    url = row.get("url") or ""
    try:
        from core.miniflux_client import get_miniflux_client
        mf_entry = get_miniflux_client().get_entry(entry_id)
        if mf_entry and mf_entry.get("url"):
            url = mf_entry["url"]
    except Exception:
        pass

    import os
    lan_ip = os.environ.get("LAN_IP", "127.0.0.1")
    miniflux_url = f"http://{lan_ip}:18080/unread/entry/{entry_id}"

    from core.rules_store import match_article_rules, load_rules
    rules = load_rules()
    rule_match = match_article_rules(row, rules)
    recent_actions = [a for a in _shared.read_actions() if str(a.get("advice", {}).get("entry_id") or a.get("entry_id")) == str(entry_id)]
    pipeline_trace = row.get("pipeline_trace") or {
        "stage": "heuristic_fast_path" if row.get("fast_path") else ("cached" if row.get("cached") else "llm_judged"),
        "base_score": row.get("base_score", row.get("score")),
        "feed_weight": row.get("feed_weight", 100),
        "final_score": row.get("score"),
        "rule_match": rule_match,
        "reason": row.get("reason"),
    }

    return jsonify({
        "version": "benchmark-detail-v1",
        "entry_id": entry_id,
        "title": row.get("title"),
        "url": url,
        "miniflux_url": miniflux_url,
        "score": row.get("score"),
        "judge": row.get("judge", {}),
        "taxonomy": taxonomy,
        "taxonomy_feedback": override,
        "human_review": _shared.read_benchmark_reviews().get(str(entry_id)),
        "rule_match": rule_match,
        "pipeline_trace": pipeline_trace,
        "recent_actions": recent_actions[-3:],
    })


@scoring_bp.post("/api/benchmark/<int:entry_id>/re-evaluate")
def benchmark_re_evaluate(entry_id):
    """Re-evaluate an article against latest rules and update score/state."""
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    row = rows.get(str(entry_id))
    if not row:
        return jsonify({"error": "entry_not_found"}), 404
    from core.rules_store import load_rules, match_article_rules
    from core.auto_actions import auto_star_entry, auto_silence_entry
    rules = load_rules()
    rm = match_article_rules(row, rules)
    sc = float(row.get("base_score") or row.get("score") or 50.0)

    bonus = 15.0 if rm.get("boosted") else (-15.0 if rm.get("demoted") else 0.0)
    new_score = round(min(100.0, max(0.0, sc + bonus))) if not rm.get("muted") else min(round(sc), 15)
    row["score"] = new_score

    if rm.get("muted") or new_score < 25:
        auto_silence_entry(entry_id, new_score, is_muted=rm.get("muted"), mute_reasons=rm.get("mute_reasons"))
    elif rm.get("boosted") or new_score >= 75:
        auto_star_entry(entry_id, new_score, is_boosted=rm.get("boosted"))

    return jsonify({
        "version": "benchmark-re-evaluate-v1",
        "entry_id": entry_id,
        "updated_score": new_score,
        "rule_match": rm,
        "message": f"已使用最新规则重新研判文章 #{entry_id}，最新评分：{new_score}/100"
    })


@scoring_bp.get("/api/scoring/ai-recommendation/<int:entry_id>")
def ai_recommendation(entry_id):
    """V102 read-only AI review suggestion card."""
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    row = rows.get(str(entry_id))
    if not row:
        return jsonify({"error": "entry_not_found"}), 404
    triage = triage_for(row)
    action = triage.get("triage") or "review"
    labels = {"keep": "建议保留", "ignore": "建议忽略", "archive": "建议归档", "review": "建议人工判断",
              "priority_candidate": "建议优先阅读", "archive_candidate": "建议归档"}
    tax = (row.get("judge", {}) or {}).get("taxonomy") or row.get("taxonomy") or {}
    reasons = []
    if row.get("reason"):
        reasons.append(str(row["reason"]))
    if tax.get("content_type"):
        reasons.append("内容类型：" + str(tax["content_type"]))
    if isinstance(tax.get("topics"), list) and tax["topics"]:
        reasons.append("主题命中：" + "、".join(map(str, tax["topics"][:3])))
    if isinstance(tax.get("matched_keywords"), list) and tax["matched_keywords"]:
        reasons.append("关键词命中：" + "、".join(map(str, tax["matched_keywords"][:3])))
    confidence = float(triage.get("confidence") or 0)
    risk = "低" if confidence >= 0.9 else "中" if confidence >= 0.75 else "需人工确认"
    return jsonify({"version": "ai-recommendation-v2", "entry_id": entry_id, "recommendation": action,
                    "recommendation_label": labels.get(action, action), "confidence": confidence,
                    "reasons": reasons[:6], "risk_level": risk,
                    "model_version": row.get("model_version") or "shadow"})


@scoring_bp.post("/api/scoring/ai-recommendation/<int:entry_id>/accept")
def ai_recommendation_accept(entry_id):
    """Accept an AI suggestion as a benchmark decision; never mutates Miniflux."""
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    row = rows.get(str(entry_id))
    if not row:
        return jsonify({"error": "entry_not_found"}), 404
    triage = triage_for(row)
    action = triage.get("triage") or "review"
    mapping = {"priority_candidate": "keep", "keep": "keep",
               "archive_candidate": "archive", "archive": "archive", "ignore": "ignore"}
    status = mapping.get(action)
    if status is None:
        return jsonify({"error": "recommendation_requires_human_decision", "recommendation": action}), 409
    confidence = float(triage.get("confidence") or 0)
    import datetime
    saved = {"entry_id": entry_id, "status": status, "category": "接受AI建议",
             "human_score": None, "score_range": None,
             "notes": f"[ai_accept] {action}（置信度 {round(confidence * 100)}%）",
             "ai_recommendation": action, "ai_confidence": confidence,
             "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    _shared.write_benchmark_review(saved)
    return jsonify({"saved": True, "executed": False, "review": saved})


@scoring_bp.post("/api/scoring/ai-recommendation/<int:entry_id>/feedback")
def ai_recommendation_feedback(entry_id):
    """Save a human override/feedback for an AI suggestion without production side effects."""
    rows = {str(r.get("entry_id")): r for r in _shared.read_scoring_rows()}
    row = rows.get(str(entry_id))
    if not row:
        return jsonify({"error": "entry_not_found"}), 404
    data = request.get_json(silent=True) or {}
    status = data.get("status") or data.get("decision")
    if status not in {"keep", "archive", "ignore"}:
        return jsonify({"error": "status_must_be_keep_archive_or_ignore"}), 400
    reasons = data.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    reasons = [str(x).strip()[:40] for x in reasons if str(x).strip()][:8]
    notes = str(data.get("notes") or "").strip()[:1000]
    triage = triage_for(row)
    action = triage.get("triage") or "review"
    confidence = float(triage.get("confidence") or 0)
    prefix = f"[ai_override] {action} → {status}"
    if reasons:
        prefix += " [feedback:" + ",".join(reasons) + "]"
    if notes:
        prefix += " " + notes
    import datetime
    saved = {"entry_id": entry_id, "status": status, "category": "修改AI建议",
             "human_score": None, "score_range": None, "notes": prefix,
             "ai_recommendation": action, "ai_confidence": confidence,
             "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    _shared.write_benchmark_review(saved)
    return jsonify({"saved": True, "executed": False, "review": saved})


@scoring_bp.get("/api/benchmark/pre-review")
def benchmark_pre_review():
    """Algorithmic pre-review of the pending queue (read-only, no writes).

    Returns each pending article with a suggested decision (keep/archive/
    boundary) and the deterministic signals behind it, to speed up human
    confirmation.  Never mutates Miniflux or the benchmark store.
    """
    from core.pre_review import DONE_STATUSES, pre_review_items
    rows = _shared.read_scoring_rows()
    reviews = _shared.read_benchmark_reviews()
    pending = []
    for row in rows:
        eid = str(row.get("entry_id"))
        review = reviews.get(eid, {"status": "pending"})
        if review.get("status") not in DONE_STATUSES:
            pending.append(row)
    return jsonify(pre_review_items(pending))


@scoring_bp.post("/api/benchmark/pre-review/accept")
def benchmark_pre_review_accept():
    """Batch-accept the algorithmic pre-review suggestions.

    Accepts one of: keep / archive (only those two are auto-appliable;
    boundary items always stay for manual review).  Writes benchmark review
    decisions ONLY — never executes Miniflux archive, never enables
    production actions.  Marked-archive items go to the explicit archive
    queue for human execution.
    """
    import datetime
    data = request.get_json(silent=True) or {}
    suggestion = data.get("suggestion")
    if suggestion not in {"keep", "archive"}:
        return jsonify({"error": "suggestion_must_be_keep_or_archive"}), 400

    from core.pre_review import DONE_STATUSES, pre_review_items
    rows = _shared.read_scoring_rows()
    reviews = _shared.read_benchmark_reviews()
    pending = []
    for row in rows:
        eid = str(row.get("entry_id"))
        review = reviews.get(eid, {"status": "pending"})
        if review.get("status") not in DONE_STATUSES:
            pending.append(row)
    items = pre_review_items(pending)["items"]

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    status = "keep" if suggestion == "keep" else "archive"
    category = "保留" if suggestion == "keep" else "标记归档"
    written = []
    skipped = []
    for x in items:
        if x["suggestion"] != suggestion:
            skipped.append(x["entry_id"])
            continue
        _shared.write_benchmark_review({
            "entry_id": x["entry_id"],
            "status": status,
            "category": f"[pre-review] {category}",
            "human_score": None,
            "score_range": None,
            "notes": f"[pre-review] {x['label']}：{'；'.join(x['reasons'][:3])}",
            "reviewed_at": now,
        })
        written.append(x["entry_id"])

    return jsonify({
        "version": "pre-review-accept-v1",
        "suggestion": suggestion,
        "executed": False,
        "written": len(written),
        "skipped_as_different_or_boundary": len(skipped),
        "entry_ids": written,
        "message": f"已按预审核建议批量标记 {len(written)} 篇为「{category}」；未执行 Miniflux 归档，标记归档的需在待归档清单中人工执行。",
    })
