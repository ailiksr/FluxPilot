"""Control-console read models for AI Worker.

The console is not a second reader. Ordinary AI decisions are informational;
only destructive archive candidates are exposed for human review.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

DATA = Path(os.environ.get('AI_WORKER_DATA_DIR', '/app/data'))


def _jsonl(name: str) -> list[dict[str, Any]]:
    path = DATA / name
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding='utf8').splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def archive_review_queue() -> list[dict[str, Any]]:
    """Return only explicit archive marks awaiting a production action."""
    try:
        from core.storage import read_reviews, read_scoring
        review_rows = read_reviews(lambda: _jsonl('benchmark_reviews.jsonl'))
        score_rows = read_scoring(lambda: _jsonl('scoring_results.jsonl'))
        reviews = {}
        for row in review_rows.values():
            eid = str(row.get('entry_id'))
            if row.get('status') == 'archive': reviews[eid] = row
            elif row.get('status') in ('pending', 'executed'): reviews.pop(eid, None)
        scores = {str(row.get('entry_id')): row for row in score_rows}
    except Exception:
        reviews = {}
        for row in _jsonl('benchmark_reviews.jsonl'):
            eid = str(row.get('entry_id'))
            if row.get('status') == 'archive': reviews[eid] = row
            elif row.get('status') in ('pending', 'executed'): reviews.pop(eid, None)
        scores = {str(row.get('entry_id')): row for row in _jsonl('scoring_results.jsonl')}
    result = []
    for eid, review in reviews.items():
        score = scores.get(eid, {})
        result.append({
            'entry_id': int(eid) if eid.isdigit() else eid,
            'title': score.get('title', review.get('title', f'文章 #{eid}')),
            'score': score.get('score'),
            'confidence': score.get('confidence'),
            'marked_at': review.get('reviewed_at', review.get('at')),
            'reason': review.get('notes') or '人工标记为待归档',
            'requires_human_review': True,
            'executed': False,
        })
    return sorted(result, key=lambda x: str(x.get('marked_at') or ''), reverse=True)


def summary() -> dict[str, Any]:
    try:
        from core.storage import read_scoring
        scores = read_scoring(lambda: _jsonl('scoring_results.jsonl'))
    except Exception:
        scores = _jsonl('scoring_results.jsonl')
    latest = {}
    for row in scores:
        latest[str(row.get('entry_id'))] = row
    autonomous = []
    try:
        from core.autonomous_policy import decide
        for row in latest.values():
            autonomous.append(decide(row))
    except Exception:
        autonomous = []
    counts = Counter(x.get('decision') for x in autonomous)
    try:
        from core.storage import read_actions, read_reviews
        reviews = list(read_reviews(lambda: _jsonl('benchmark_reviews.jsonl')).values())
        actions = read_actions(lambda: _jsonl('feed_advice_actions.jsonl'))
    except Exception:
        reviews = _jsonl('benchmark_reviews.jsonl')
        actions = _jsonl('feed_advice_actions.jsonl')
    queue = archive_review_queue()
    fast_path_count = sum(1 for row in latest.values() if row.get('fast_path') or (isinstance(row.get('pipeline_trace'), dict) and row['pipeline_trace'].get('fast_path')))
    return {
        'version': 'control-console-v1',
        'role': 'operations_console',
        'reader_link': 'Use Miniflux/Reactflux for reading; this console manages policy and exceptions.',
        'articles_scored': len(latest),
        'fast_path_intercepted': fast_path_count,
        'autonomous': {key: counts.get(key, 0) for key in ('priority', 'keep', 'skip', 'review')},
        'ordinary_human_actions': sum(1 for r in reviews if r.get('status') in {'keep', 'ignore'}),
        'archive_review_required': len(queue),
        'archive_executed_actions': sum(1 for r in actions if r.get('action') == 'article_archive_approved'),
        'production_actions_enabled': False,
        'human_scope': 'archive_exceptions_only',
    }
