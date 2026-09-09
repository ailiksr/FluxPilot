"""V131 diagnostics routes extracted from scoring.py; compatibility-safe."""
from flask import jsonify
from app.routes.scoring import scoring_bp, _read, _feed_quality_map, scoring_backtest
from app.routes.reviews import benchmark_reviewed

@scoring_bp.get("/api/console/summary")
def console_summary():
    from core.control_console import summary
    return jsonify(summary())


@scoring_bp.get("/api/console/archive-review")
def console_archive_review():
    from core.control_console import archive_review_queue
    items = archive_review_queue()
    return jsonify({"version":"control-console-v1", "requires_human_review":True,
                    "production_unchanged":True, "count":len(items), "items":items})


@scoring_bp.get("/api/scoring/error-analysis")
def scoring_error_analysis():
    """Read-only feedback loop report from human decisions vs shadow suggestions."""
    from collections import Counter
    rows=[]
    try:
        reviewed = benchmark_reviewed().get_json().get("items", [])
    except Exception:
        reviewed=[]
    mismatches=Counter(); decisions=Counter()
    for r in reviewed:
        h=(r.get("human_review") or {}).get("status")
        t=(r.get("triage") or {}).get("route", "unknown")
        decisions[(t,h)]+=1
        if h and t not in (h,"review"):
            mismatches[(t,h)]+=1
    for (ai,h),n in mismatches.most_common():
        rows.append({"ai_route":ai,"human_result":h,"count":n,"suggestion":"检查该规则权重或增加样本","next_step":"查看决策依据明细"})
    return jsonify({"version":"error-analysis-v2","reviewed":len(reviewed),"production_unchanged":True,"mismatches":rows,"decision_pairs":[{"ai":a,"human":h,"count":n} for (a,h),n in decisions.items()]})


@scoring_bp.get("/api/scoring/simulation")
def scoring_simulation():
    """Read-only weight simulation. It never writes policy or production data."""
    from flask import request
    from core.scoring_dimensions_v1 import shadow_breakdown
    q=float(request.args.get("quality_weight",0.45))
    p=float(request.args.get("preference_weight",0.55))
    total=q+p
    if total<=0: total=1
    q/=total; p/=total
    rows=[]
    for r in _read():
        j=r.get("judge") or {}
        t=j.get("taxonomy") or r.get("taxonomy") or {}
        if "interest_match" not in t: continue
        d=shadow_breakdown(r,0)
        score=d["quality_score"]*q+d["preference_score"]*p
        rows.append(score)
    return jsonify({"version":"weight-simulation-v1","production_unchanged":True,"weights":{"quality":round(q,3),"preference":round(p,3)},"sample_count":len(rows),"candidates":{"above80":sum(x>=80 for x in rows),"below25":sum(x<25 for x in rows)}})


@scoring_bp.get("/api/scoring/assist-gate")
def scoring_assist_gate():
    """V100 assistant mode gate. Suggests only; never executes production actions."""
    bt = scoring_backtest().get_json()
    m = bt.get("metrics") or {}
    return jsonify({
        "version":"assist-gate-v1",
        "mode":"ai_suggest_human_confirm",
        "production_actions_enabled":False,
        "suggestion_enabled": True,
        "criteria": {
            "requires_human_confirm": True,
            "keep_precision": m.get("keep_precision"),
            "negative_precision": m.get("negative_precision")
        },
        "message":"AI 仅提出建议，最终操作需要人工确认。"
    })


@scoring_bp.get("/api/scoring/triage")
def scoring_triage():
    """Read-only shadow auto-routing report; never mutates Miniflux or production scores."""
    from core.preference_profile import build_profile, learned_interest
    from core.scoring_dimensions_v1 import shadow_breakdown
    rows = _read(); profile = build_profile(); items=[]
    for r in rows:
        t=(r.get("judge") or {}).get("taxonomy") or r.get("taxonomy") or {}
        correction=learned_interest(t, profile) or 0
        d=shadow_breakdown(r, correction)
        if not d.get("available"): continue
        conf=float(r.get("confidence") or 0)
        if conf >= .82 and d["final_shadow_score"] >= 80 and d["promotion_score"] < 60:
            route="auto_keep_candidate"
        elif conf >= .82 and d["final_shadow_score"] < 25 and d["promotion_score"] < 60:
            route="auto_ignore_candidate"
        else:
            route="human_review"
        items.append({"entry_id":r.get("entry_id"),"title":r.get("title"),"route":route,"confidence":conf,"shadow":d})
    counts={k:sum(1 for x in items if x["route"]==k) for k in ("auto_keep_candidate","auto_ignore_candidate","human_review")}
    return jsonify({"version":"triage-shadow-v1","production_unchanged":True,"profile_samples":profile["samples"],"ready":profile["ready"],"counts":counts,"items":items})


@scoring_bp.get("/api/scoring/article-signals")
def scoring_article_signals():
    from core.article_signals import enrich as enrich_article_signals
    from core.autonomous_policy import decide as autonomous_decide
    rows = enrich_article_signals(_read())
    fq = _feed_quality_map()
    items = [{"entry_id": r.get("entry_id"), "title": r.get("title"),
              "feed_id": r.get("feed_id"), **(r.get("article_signals") or {}),
              "autonomous": autonomous_decide(r, fq.get(str(r.get("feed_id")), 50))}
             for r in rows]
    return jsonify({"version":"article-signals-v1", "production_unchanged":True,
                    "duplicate_count":sum(1 for x in items if x.get("duplicate")),
                    "items":items})


@scoring_bp.get("/api/scoring/autonomous")
def scoring_autonomous():
    """Explainable AI-first attention routing; never changes Miniflux state."""
    from core.autonomous_policy import decide as autonomous_decide
    from core.article_signals import enrich as enrich_article_signals
    rows = enrich_article_signals(_read())
    feed_quality = _feed_quality_map()
    items = []
    for row in rows:
        decision = autonomous_decide(row, feed_quality.get(str(row.get("feed_id")), 50))
        items.append({"entry_id": row.get("entry_id"), "title": row.get("title"),
                      "score": row.get("score"), "feed_id": row.get("feed_id"), **decision})
    counts = {key: sum(1 for item in items if item["decision"] == key)
              for key in ("priority", "keep", "skip", "review")}
    return jsonify({"version": "autonomous-policy-v1", "production_unchanged": True,
                    "human_review_recommended": counts["review"], "counts": counts,
                    "items": items})


@scoring_bp.get("/api/scoring/feed-health")
def scoring_feed_health():
    from core.feed_health import report
    return jsonify({"version":"feed-health-v1","production_unchanged":True,"items":report()})


@scoring_bp.get("/api/scoring/feed-health/trends")
def scoring_feed_health_trends():
    """Read-only long-term fetch health trends (success rate / latency / errors)."""
    from flask import request
    from core.feed_health import trends
    hours = request.args.get("hours", "24")
    try:
        hours = max(1, min(168, int(hours)))
    except (TypeError, ValueError):
        hours = 24
    return jsonify(trends(hours=hours))


@scoring_bp.get("/api/scoring/feed-quality-v2")
def scoring_feed_quality_v2():
    from core.feed_quality_v2 import build_quality_report
    rows = _read()
    items = build_quality_report(rows)
    try:
        from core.feed_health import report as health_report
        health = {str(x.get("feed_id")): x for x in health_report()}
        for item in items:
            item["health"] = health.get(str(item.get("feed_id")))
    except Exception:
        pass
    return jsonify({"version": "feed-quality-v2", "production_unchanged": True,
                    "items": items})


@scoring_bp.get("/api/scoring/feed-quality")
def scoring_feed_quality():
    """Read-only RSS source quality summary from scoring ledger."""
    from collections import defaultdict
    rows=_read()
    feeds=defaultdict(list)
    for r in rows:
        if r.get("feed_id") is not None and isinstance(r.get("score"), (int,float)):
            feeds[str(r.get("feed_id"))].append(r.get("score"))
    result=[]
    for fid,scores in feeds.items():
        if not scores: continue
        result.append({"feed_id":fid,"sample_size":len(scores),"average_score":round(sum(scores)/len(scores),1),"low_rate":round(sum(x<25 for x in scores)/len(scores),2)})
    result.sort(key=lambda x:(-x["sample_size"],x["average_score"]))
    return jsonify({"version":"feed-quality-v1","production_unchanged":True,"feeds":result})


@scoring_bp.get("/api/scoring/trends")
def scoring_trends():
    """Read-only topic/keyword/content-type/feed trends from the scoring ledger.

    Inspired by mature RSS-AI projects (newscope topic preferences, rss-ai
    trend analysis).  Reports are derived from the existing taxonomy and score
    rows; no LLM call, no Miniflux write, production unchanged.
    """
    from collections import Counter, defaultdict
    from datetime import datetime, timedelta, timezone
    rows = _read()
    now = datetime.now(timezone.utc)
    topics_all = Counter()
    topics_recent7 = Counter()
    topics_recent30 = Counter()
    keywords = Counter()
    content_types = Counter()
    feed_activity = defaultdict(lambda: {"count": 0, "scores": []})
    scored_total = 0
    for r in rows:
        score = r.get("score")
        if not isinstance(score, (int, float)):
            continue
        scored_total += 1
        judge = r.get("judge") or {}
        tax = judge.get("taxonomy") or r.get("taxonomy") or {}
        ts = r.get("scored_at") or ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            dt = None
        age = (now - dt).days if dt else None
        topics = tax.get("topics") or []
        kws = tax.get("matched_keywords") or []
        ctype = tax.get("content_type") or "unknown"
        for t in topics:
            topics_all[str(t)] += 1
            if age is not None and age <= 7:
                topics_recent7[str(t)] += 1
            if age is not None and age <= 30:
                topics_recent30[str(t)] += 1
        for k in kws:
            keywords[str(k)] += 1
        content_types[str(ctype)] += 1
        fid = r.get("feed_id")
        if fid is not None:
            fa = feed_activity[str(fid)]
            fa["count"] += 1
            fa["scores"].append(score)
    # Topic momentum: recent7 share vs all-time share (rising = trending up)
    total_7 = sum(topics_recent7.values()) or 1
    total_all = sum(topics_all.values()) or 1
    topic_trends = []
    for t, cnt in topics_all.most_common(20):
        recent = topics_recent7.get(t, 0)
        share_all = cnt / total_all
        share_7 = recent / total_7
        momentum = round(share_7 - share_all, 4) if cnt >= 3 else None
        topic_trends.append({"topic": t, "count": cnt, "recent7": recent,
                             "recent30": topics_recent30.get(t, 0),
                             "share": round(share_all * 100, 1),
                             "momentum": momentum,
                             "trending": momentum is not None and momentum > 0.01})
    topic_trends.sort(key=lambda x: (x["trending"], x["momentum"] or -1, x["count"]), reverse=True)
    feed_stats = []
    for fid, fa in feed_activity.items():
        scores = fa["scores"]
        feed_stats.append({
            "feed_id": fid,
            "articles": fa["count"],
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "high_rate": round(sum(1 for s in scores if s >= 80) / len(scores), 3) if scores else 0,
            "low_rate": round(sum(1 for s in scores if s < 25) / len(scores), 3) if scores else 0,
        })
    feed_stats.sort(key=lambda x: (-x["articles"], -(x["avg_score"] or 0)))
    return jsonify({
        "version": "trends-v1",
        "production_unchanged": True,
        "scored_total": scored_total,
        "topic_trends": topic_trends[:15],
        "top_keywords": [{"keyword": k, "count": v} for k, v in keywords.most_common(20)],
        "content_types": [{"type": k, "count": v} for k, v in content_types.most_common()],
        "feed_activity": feed_stats[:20],
    })




@scoring_bp.get("/api/system-health")
def system_health():
    """Read-only aggregated system health: LLM, storage, summary, outbox."""
    from core.system_health import report
    return jsonify(report())
