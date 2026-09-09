"""User rules storage and evaluation engine (Feedly Leo & newscope pattern).

Allows users to set macro rules (boost topics, boost keywords, mute topics,
mute keywords, demote keywords, mute content types) so AI can triage automatically
without requiring manual micro-scoring.

Stored in data/user_rules.json with transactional writes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from common.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(os.environ.get("AI_WORKER_DATA_DIR", "/app/data"))
RULES_FILE = DATA_DIR / "user_rules.json"
VERSION = "user-rules-v1"

DEFAULT_RULES: dict[str, Any] = {
    "version": VERSION,
    "boost_topics": ["AI", "技术", "架构", "社会", "文化", "互联网"],
    "boost_keywords": ["AI", "大模型", "智能体", "开源", "深度学习", "Python", "算法"],
    "mute_topics": [],
    "mute_keywords": [
        "领券", "包邮", "折扣", "优惠", "实用的玩意儿", "番号",
        "水牛奶鸡蛋糕", "牙膏", "羊排", "干红", "返利", "立减", "买一送一"
    ],
    "demote_keywords": ["评测", "开箱", "短剧", "吐槽"],
    "mute_content_types": ["deal"],
    "auto_star": True,
    "auto_silence": True,
}


def _clean_str_list(items: Any, max_len: int = 50, limit: int = 100) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen = set()
    for item in items:
        val = str(item or "").strip()
        if val and val not in seen:
            seen.add(val)
            out.append(val[:max_len])
        if len(out) >= limit:
            break
    return out


def load_rules() -> dict[str, Any]:
    """Load active rules from user_rules.json or fallback to defaults."""
    if not RULES_FILE.exists():
        return dict(DEFAULT_RULES)
    try:
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(DEFAULT_RULES)
        return {
            "version": VERSION,
            "boost_topics": _clean_str_list(data.get("boost_topics", DEFAULT_RULES["boost_topics"])),
            "boost_keywords": _clean_str_list(data.get("boost_keywords", DEFAULT_RULES["boost_keywords"])),
            "mute_topics": _clean_str_list(data.get("mute_topics", DEFAULT_RULES["mute_topics"])),
            "mute_keywords": _clean_str_list(data.get("mute_keywords", DEFAULT_RULES["mute_keywords"])),
            "demote_keywords": _clean_str_list(data.get("demote_keywords", DEFAULT_RULES.get("demote_keywords", []))),
            "mute_content_types": _clean_str_list(data.get("mute_content_types", DEFAULT_RULES["mute_content_types"])),
            "auto_star": bool(data.get("auto_star", True)),
            "auto_silence": bool(data.get("auto_silence", True)),
            "updated_at": data.get("updated_at"),
        }
    except Exception as e:
        logger.warning(f"Failed to load user rules, using defaults: {e}")
        return dict(DEFAULT_RULES)


def save_rules(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist user rules atomically."""
    import datetime

    rules = {
        "version": VERSION,
        "boost_topics": _clean_str_list(payload.get("boost_topics", [])),
        "boost_keywords": _clean_str_list(payload.get("boost_keywords", [])),
        "mute_topics": _clean_str_list(payload.get("mute_topics", [])),
        "mute_keywords": _clean_str_list(payload.get("mute_keywords", [])),
        "demote_keywords": _clean_str_list(payload.get("demote_keywords", [])),
        "mute_content_types": _clean_str_list(payload.get("mute_content_types", [])),
        "auto_star": bool(payload.get("auto_star", True)),
        "auto_silence": bool(payload.get("auto_silence", True)),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = RULES_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(RULES_FILE)
    logger.info("Saved user preference and mute rules")
    return rules


def match_article_rules(row: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check an article against active user rules (title, topics, keywords, type, content tail)."""
    if rules is None:
        rules = load_rules()

    title = str(row.get("title") or "").lower()
    judge = row.get("judge") or {}
    tax = judge.get("taxonomy") or row.get("taxonomy") or {}
    topics = [str(t).lower() for t in (tax.get("topics") or [])]
    keywords = [str(k).lower() for k in (tax.get("matched_keywords") or [])]
    ctype = str(judge.get("content_type") or tax.get("content_type") or "").strip().lower()
    content_tail = str(row.get("content") or "")[-500:].lower()

    mute_reasons: list[str] = []
    demote_reasons: list[str] = []
    boost_reasons: list[str] = []

    # 1. Content type mute
    for mc in rules.get("mute_content_types", []):
        if ctype == str(mc).lower():
            mute_reasons.append(f"内容类型已屏蔽: {ctype}")

    # 2. Mute topics
    for mt in rules.get("mute_topics", []):
        mt_low = str(mt).lower()
        if mt_low in topics or mt_low in title:
            mute_reasons.append(f"命中屏蔽主题: {mt}")

    # 3. Mute keywords (title, taxonomy keywords, or content tail)
    for mk in rules.get("mute_keywords", []):
        mk_low = str(mk).lower()
        if mk_low in title or any(mk_low in k for k in keywords):
            mute_reasons.append(f"命中屏蔽关键词: {mk}")
        elif content_tail and mk_low in content_tail:
            mute_reasons.append(f"正文尾部命中屏蔽词: {mk}")

    # 4. Demote keywords (soft penalty)
    for dk in rules.get("demote_keywords", []):
        dk_low = str(dk).lower()
        if dk_low in title or any(dk_low in k for k in keywords):
            demote_reasons.append(f"命中轻度降权词: {dk}")

    # 5. Boost topics (only if not muted)
    for bt in rules.get("boost_topics", []):
        bt_low = str(bt).lower()
        if bt_low in topics or bt_low in title:
            boost_reasons.append(f"命中关注主题: {bt}")

    # 6. Boost keywords
    for bk in rules.get("boost_keywords", []):
        bk_low = str(bk).lower()
        if bk_low in title or any(bk_low in k for k in keywords):
            boost_reasons.append(f"命中关注关键词: {bk}")

    return {
        "muted": len(mute_reasons) > 0,
        "demoted": len(demote_reasons) > 0 and len(mute_reasons) == 0,
        "boosted": len(boost_reasons) > 0 and len(mute_reasons) == 0,
        "mute_reasons": list(dict.fromkeys(mute_reasons)),
        "demote_reasons": list(dict.fromkeys(demote_reasons)),
        "boost_reasons": list(dict.fromkeys(boost_reasons)),
    }


def get_rules_hit_counts(rows: list[dict[str, Any]], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Calculate real hit counts for every active rule keyword/topic across scored rows."""
    if rules is None:
        rules = load_rules()

    boost_kw_hits = {k: 0 for k in rules.get("boost_keywords", [])}
    boost_top_hits = {k: 0 for k in rules.get("boost_topics", [])}
    mute_kw_hits = {k: 0 for k in rules.get("mute_keywords", [])}
    mute_top_hits = {k: 0 for k in rules.get("mute_topics", [])}
    demote_kw_hits = {k: 0 for k in rules.get("demote_keywords", [])}

    for r in rows:
        title = str(r.get("title") or "").lower()
        judge = r.get("judge") or {}
        tax = judge.get("taxonomy") or r.get("taxonomy") or {}
        topics = [str(t).lower() for t in (tax.get("topics") or [])]
        keywords = [str(k).lower() for k in (tax.get("matched_keywords") or [])]
        content_tail = str(r.get("content") or "")[-500:].lower()

        for bk in boost_kw_hits:
            bk_l = bk.lower()
            if bk_l in title or any(bk_l in k for k in keywords):
                boost_kw_hits[bk] += 1

        for bt in boost_top_hits:
            bt_l = bt.lower()
            if bt_l in topics or bt_l in title:
                boost_top_hits[bt] += 1

        for mk in mute_kw_hits:
            mk_l = mk.lower()
            if mk_l in title or any(mk_l in k for k in keywords) or (content_tail and mk_l in content_tail):
                mute_kw_hits[mk] += 1

        for mt in mute_top_hits:
            mt_l = mt.lower()
            if mt_l in topics or mt_l in title:
                mute_top_hits[mt] += 1

        for dk in demote_kw_hits:
            dk_l = dk.lower()
            if dk_l in title or any(dk_l in k for k in keywords):
                demote_kw_hits[dk] += 1

    return {
        "boost_keywords": boost_kw_hits,
        "boost_topics": boost_top_hits,
        "mute_keywords": mute_kw_hits,
        "mute_topics": mute_top_hits,
        "demote_keywords": demote_kw_hits,
    }


def get_rule_hits(keyword: str, rule_type: str, rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve articles that matched a specific rule keyword."""
    kw_low = str(keyword or "").strip().lower()
    if not kw_low:
        return []

    matched = []
    for r in rows:
        title = str(r.get("title") or "")
        title_low = title.lower()
        judge = r.get("judge") or {}
        tax = judge.get("taxonomy") or r.get("taxonomy") or {}
        topics = [str(t).lower() for t in (tax.get("topics") or [])]
        keywords = [str(k).lower() for k in (tax.get("matched_keywords") or [])]
        content_tail = str(r.get("content") or "")[-500:].lower()

        hit = False
        if "topic" in rule_type:
            hit = kw_low in topics or kw_low in title_low
        else:
            hit = kw_low in title_low or any(kw_low in k for k in keywords) or (content_tail and kw_low in content_tail)

        if hit:
            matched.append({
                "entry_id": r.get("entry_id"),
                "title": title,
                "score": r.get("score"),
                "feed_id": r.get("feed_id"),
                "published_at": r.get("published_at") or r.get("scored_at"),
            })
            if len(matched) >= limit:
                break

    return matched


def simulate_rule(keyword: str, rule_type: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sandbox simulation for an uncommitted rule.

    Checks how many existing articles would be hit, identifies low-score hits (good matches),
    and warns if high-score articles (score >= 70) would be unintentionally affected.
    """
    kw_low = str(keyword or "").strip().lower()
    if not kw_low:
        return {
            "keyword": "",
            "rule_type": rule_type,
            "total_hits": 0,
            "high_score_count": 0,
            "low_score_count": 0,
            "warning": None,
            "sample_titles": [],
        }

    hits: list[str] = []
    high_scores: list[str] = []
    low_scores: list[str] = []

    for r in rows:
        title = str(r.get("title") or "")
        title_low = title.lower()
        judge = r.get("judge") or {}
        tax = judge.get("taxonomy") or r.get("taxonomy") or {}
        topics = [str(t).lower() for t in (tax.get("topics") or [])]
        keywords = [str(k).lower() for k in (tax.get("matched_keywords") or [])]
        content_tail = str(r.get("content") or "")[-500:].lower()

        hit = False
        if "topic" in rule_type:
            hit = kw_low in topics or kw_low in title_low
        else:
            hit = kw_low in title_low or any(kw_low in k for k in keywords) or (content_tail and kw_low in content_tail)

        if hit:
            sc = r.get("score")
            hits.append(title)
            if sc is not None and sc >= 70:
                high_scores.append(title)
            elif sc is not None and sc < 35:
                low_scores.append(title)

    warning = None
    if "mute" in rule_type or "demote" in rule_type:
        if high_scores:
            warning = f"⚠️ 警示：该规则将命中 {len(high_scores)} 篇高分（≥70分）文章，可能存在误伤优质内容的风险！"
    elif "boost" in rule_type:
        if low_scores:
            warning = f"ℹ️ 提示：该关注词包含 {len(low_scores)} 篇低质文章，可能将部分水文提权至精选。"

    return {
        "keyword": keyword,
        "rule_type": rule_type,
        "total_hits": len(hits),
        "high_score_count": len(high_scores),
        "low_score_count": len(low_scores),
        "warning": warning,
        "sample_titles": hits[:5],
    }


apply_rules = match_article_rules
