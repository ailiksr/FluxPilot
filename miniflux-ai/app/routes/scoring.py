import json
import fcntl
from pathlib import Path
import os
from flask import render_template, request, Blueprint, jsonify, Response
from core.feed_advisor import build_advice
from core.advice_store import record
from core.feed_policy import set_weight, rollback, apply_weight, get_weight
from core.article_actions import archive_entry, restore_entry
from core.miniflux_client import get_miniflux_client
from core.triage import triage_for
from core.taxonomy import taxonomy_status
from core.scoring_dimensions_v1 import shadow_breakdown
from core.preference_profile import build_profile
from core.automation_gate import evaluate as automation_gate

from app.routes import _shared  # noqa: F401  (shared data helpers)

scoring_bp = Blueprint("scoring", __name__)


def api_response(version, **payload):
    """Canonical response envelope for migrated routes; legacy routes stay byte-compatible."""
    return jsonify({"version": version, **payload})


# ---------------------------------------------------------------------------
# Backward-compatible aliases for helpers now owned by _shared.
# diagnostics.py and other modules import these names from here.
# ---------------------------------------------------------------------------
_read = _shared.read_scoring_rows
_feed_quality_map = _shared.feed_quality_map
_actions_read = _shared.read_actions
_benchmark_read = _shared.read_benchmark_reviews
_benchmark_write = _shared.write_benchmark_review
_taxonomy_feedback_read = _shared.read_taxonomy_feedback
_clean_list = _shared.clean_list


@scoring_bp.get("/api/scores")
def scores():
    rows = _read()
    from core.autonomous_policy import decide as autonomous_decide
    from core.article_signals import enrich as enrich_article_signals
    rows = enrich_article_signals(rows)
    feed_quality = _feed_quality_map()
    rows = [{**r, "triage": triage_for(r), "taxonomy_status": taxonomy_status(r.get("judge")),
             "autonomous": autonomous_decide(r, feed_quality.get(str(r.get("feed_id")), 50))} for r in rows]
    return jsonify({"version": "scores-v1", "count": len(rows), "items": rows})


@scoring_bp.get("/api/scoring/shadow")
def scoring_shadow():
    """Compare the proposed multi-dimensional model without changing production ranking."""
    rows = _read()
    reviews = _benchmark_read()
    profile = build_profile()
    details = []
    tagged = 0
    for r in rows:
        t = (r.get("judge") or {}).get("taxonomy") or r.get("taxonomy") or {}
        try:
            from core.preference_profile import learned_interest
            correction = learned_interest(t, profile) or 0
        except Exception:
            correction = 0
        d = shadow_breakdown(r, correction, _feed_quality_map().get(str(r.get("feed_id")), 50))
        if d.get("available"):
            tagged += 1
            human = reviews.get(str(r.get("entry_id")), {})
            if isinstance(human.get("human_score"), (int, float)):
                d["human_score"] = human["human_score"]
                d["current_score"] = r.get("score")
                d["current_abs_error"] = round(abs(float(human["human_score"]) - float(r.get("score", 0))), 2)
                d["shadow_abs_error"] = round(abs(float(human["human_score"]) - float(d["final_shadow_score"])), 2)
        details.append({"entry_id": r.get("entry_id"), "title": r.get("title"), **d})
    total = len(rows)
    return jsonify({"version": "dimensions-v1", "production_unchanged": True, "total": total,
                    "tagged": tagged, "untagged": total - tagged,
                    "coverage": round(tagged / total * 100, 1) if total else 0,
                    "profile": {"version": profile["version"], "epoch": profile["epoch"],
                                "samples": profile["samples"], "ready": profile["ready"]},
                    "items": details})


@scoring_bp.get("/api/scoring/automation-gate")
def scoring_automation_gate():
    return jsonify(automation_gate(scoring_backtest().get_json()))


@scoring_bp.get("/api/scoring/backtest")
def scoring_backtest():
    """Leave-one-out backtest of Shadow routing against new human decisions.

    The held-out article is excluded from its preference profile to avoid
    training/evaluation leakage. No Miniflux or production state is changed.
    """
    rows = _read()
    reviews = _benchmark_read()
    from core.preference_profile import learned_interest
    from collections import Counter
    items = []
    for r in rows:
        eid = str(r.get("entry_id"))
        human = reviews.get(eid)
        if not human or human.get("status") not in {"keep", "ignore", "archive"}:
            continue
        profile = build_profile(exclude_entry_id=eid)
        t = (r.get("judge") or {}).get("taxonomy") or r.get("taxonomy") or {}
        correction = learned_interest(t, profile) or 0
        d = shadow_breakdown(r, correction)
        if not d.get("available"):
            continue
        conf = float(r.get("confidence") or 0)
        if conf >= .82 and d["final_shadow_score"] >= 80 and d["promotion_score"] < 60:
            route = "keep"
        elif conf >= .82 and d["final_shadow_score"] < 25 and d["promotion_score"] >= 60:
            route = "negative"
        else:
            route = "review"
        actual = "keep" if human.get("status") == "keep" else "negative"
        items.append({"entry_id": r.get("entry_id"), "title": r.get("title"), "route": route,
                      "actual": actual, "human_status": human.get("status"),
                      "confidence": conf, "score": d["final_shadow_score"]})
    actionable = [x for x in items if x["route"] != "review"]
    tp = sum(x["route"] == "keep" and x["actual"] == "keep" for x in actionable)
    fp = sum(x["route"] == "keep" and x["actual"] == "negative" for x in actionable)
    tn = sum(x["route"] == "negative" and x["actual"] == "negative" for x in actionable)
    fn = sum(x["route"] == "negative" and x["actual"] == "keep" for x in actionable)
    coverage = len(actionable) / len(items) if items else 0
    precision = (tp / (tp + fp)) if tp + fp else None
    recall = (tp / (tp + fn)) if tp + fn else None
    negative_precision = (tn / (tn + fn)) if tn + fn else None
    accuracy = ((tp + tn) / len(actionable)) if actionable else None
    return jsonify({"version": "shadow-backtest-v2", "production_unchanged": True,
                    "evaluation": "leave_one_out", "total_reviewed": len(items),
                    "actionable": len(actionable), "review": len(items) - len(actionable),
                    "coverage": round(coverage * 100, 1),
                    "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
                    "metrics": {"accuracy": round(accuracy * 100, 1) if accuracy is not None else None,
                                "keep_precision": round(precision * 100, 1) if precision is not None else None,
                                "keep_recall": round(recall * 100, 1) if recall is not None else None,
                                "negative_precision": round(negative_precision * 100, 1) if negative_precision is not None else None},
                    "items": items})


@scoring_bp.get("/api/scoring/preference-validation")
def scoring_preference_validation():
    """V108 chronological holdout validation for the explainable preference layer."""
    from core.preference_profile import preference_probability
    rows = _read()
    reviews = _benchmark_read()
    joined = []
    for r in rows:
        h = reviews.get(str(r.get("entry_id")))
        if h and h.get("status") in {"keep", "ignore", "archive"}:
            joined.append((r, h))
    joined.sort(key=lambda x: int(x[0].get("entry_id") or 0))
    cut = max(1, int(len(joined) * .7))
    train = joined[:cut]
    test = joined[cut:]
    import tempfile
    from core import preference_profile as pp
    old = pp.REVIEWS
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf8", delete=False) as f:
            for _, h in train:
                f.write(json.dumps(h, ensure_ascii=False) + "\n")
            tmp = f.name
        pp.REVIEWS = Path(tmp)
        profile = pp.build_profile()
    finally:
        pp.REVIEWS = old
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    scored = []
    for r, h in test:
        t = (r.get("judge") or {}).get("taxonomy") or r.get("taxonomy") or {}
        p, e = preference_probability(t, profile)
        y = h.get("status") == "keep"
        scored.append((p, y, r.get("entry_id"), e))

    def metrics(th):
        tp = sum(p >= th and y for p, y, _, _ in scored)
        fp = sum(p >= th and not y for p, y, _, _ in scored)
        fn = sum(p < th and y for p, y, _, _ in scored)
        tn = sum(p < th and not y for p, y, _, _ in scored)
        return {"threshold": th, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                "precision": round(tp / (tp + fp) * 100, 1) if tp + fp else None,
                "recall": round(tp / (tp + fn) * 100, 1) if tp + fn else None,
                "coverage": round((tp + fp) / len(scored) * 100, 1) if scored else 0}
    return jsonify({"version": "preference-validation-v108", "production_unchanged": True,
                    "evaluation": "chronological_holdout_70_30", "train": len(train),
                    "test": len(test), "thresholds": [metrics(.5), metrics(.7), metrics(.8)],
                    "evidence_features": sum(e for _, _, _, e in scored)})


# feed-advice and feed-policy routes migrated to app/routes/feeds.py in V131.


# article-advice, article-archive, article-actions, recommendations routes
# migrated to app/routes/articles.py in V131.


# feed-advice GET migrated to app/routes/feeds.py in V131.


@scoring_bp.get("/api/preferences/profile")
def preference_profile():
    profile = build_profile()
    return jsonify({"version": "preference-profile-v2", **profile})


@scoring_bp.get("/api/preferences/rules")
def get_user_rules():
    """Get active boost topics/keywords and mute filters with hit statistics."""
    from core.rules_store import load_rules, get_rules_hit_counts
    rules = load_rules()
    try:
        rows = _read()
        hit_counts = get_rules_hit_counts(rows, rules)
    except Exception:
        hit_counts = {}
    return jsonify({**rules, "hit_counts": hit_counts})


@scoring_bp.post("/api/preferences/rules")
def update_user_rules():
    """Update active boost topics/keywords and mute filters."""
    from flask import request
    from core.rules_store import save_rules
    data = request.get_json(silent=True) or {}
    updated = save_rules(data)
    return jsonify({"ok": True, "rules": updated})


@scoring_bp.get("/api/preferences/rules/suggestions")
def get_rule_suggestions():
    """AI automatically mines suggested mute keywords and boost topics from history."""
    from core.rules_miner import mine_rule_suggestions
    from core.rules_store import load_rules
    try:
        rows = _read()
        rules = load_rules()
        result = mine_rule_suggestions(rows, rules)
    except Exception as e:
        result = {"version": "rules-suggestions-v1", "suggested_mutes": [], "suggested_boosts": [], "error": str(e)}
    return jsonify(result)


@scoring_bp.get("/api/preferences/rules/preview-hits")
def preview_rule_hits():
    """Retrieve articles matching a specific rule keyword."""
    from flask import request
    from core.rules_store import get_rule_hits
    keyword = request.args.get("keyword", "")
    rule_type = request.args.get("type", "mute")
    try:
        rows = _read()
        hits = get_rule_hits(keyword, rule_type, rows)
    except Exception:
        hits = []
    return jsonify({"version": "rule-hits-v1", "keyword": keyword, "type": rule_type, "count": len(hits), "items": hits})


@scoring_bp.post("/api/preferences/rules/simulate")
def simulate_rule_impact():
    """Simulate the impact of a candidate rule before saving."""
    from flask import request
    from core.rules_store import simulate_rule
    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "")
    rule_type = data.get("type", "mute")
    try:
        rows = _read()
        result = simulate_rule(keyword, rule_type, rows)
    except Exception as e:
        result = {"keyword": keyword, "rule_type": rule_type, "total_hits": 0, "warning": str(e), "sample_titles": []}
    return jsonify({"version": "rule-simulate-v1", **result})


@scoring_bp.get("/ai-worker")
def ai_worker():
    return render_template("ai_worker.html")


# Register extracted route modules after compatibility helpers are defined.
# reviews.py must be imported before diagnostics.py because diagnostics.py
# imports benchmark_reviewed from reviews.py.
from app.routes import reviews as _reviews  # noqa: E402,F401
from app.routes import articles as _articles  # noqa: E402,F401
from app.routes import feeds as _feeds  # noqa: E402,F401
from app.routes import diagnostics as _diagnostics  # noqa: E402,F401
from app.routes import mcp as _mcp  # noqa: E402,F401
