"""Long-term Feed fetch health aggregation from sampler JSONL."""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA = Path(os.environ.get('AI_WORKER_DATA_DIR', '/app/data'))
SAMPLES = DATA / 'feed_health_samples.jsonl'
VERSION = 'feed-health-v1'


def _read():
    if not SAMPLES.exists():
        return []
    rows = []
    for line in SAMPLES.read_text(encoding='utf8').splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _p95(values):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values)-1, max(0, math.ceil(len(values) * .95) - 1))], 1)


def report():
    grouped = defaultdict(list)
    for row in _read():
        grouped[str(row.get('feed_id'))].append(row)
    result = []
    for feed_id, rows in grouped.items():
        rows.sort(key=lambda x: str(x.get('sampled_at') or ''))
        ok = [r for r in rows if isinstance(r.get('status_code'), int) and 200 <= r['status_code'] < 400 and not r.get('error')]
        latencies = [float(r['latency_ms']) for r in rows if isinstance(r.get('latency_ms'), (int, float))]
        consecutive_failures = 0
        for row in reversed(rows):
            if row in ok:
                break
            consecutive_failures += 1
        action = 'healthy'
        label = '抓取正常'
        if consecutive_failures >= 3 or (rows and len(ok) / len(rows) < .5):
            action, label = 'investigate', '需要排查'
        elif consecutive_failures > 0 or (rows and len(ok) / len(rows) < .9):
            action, label = 'observe', '继续观察'
        result.append({
            'feed_id': feed_id,
            'title': rows[-1].get('title') if rows else '',
            'version': VERSION,
            'sample_count': len(rows),
            'success_count': len(ok),
            'success_rate': round(len(ok) / len(rows), 3) if rows else None,
            'average_latency_ms': round(sum(latencies) / len(latencies), 1) if latencies else None,
            'p95_latency_ms': _p95(latencies),
            'consecutive_failures': consecutive_failures,
            'last_sampled_at': rows[-1].get('sampled_at') if rows else None,
            'last_success_at': ok[-1].get('sampled_at') if ok else None,
            'action': action,
            'label': label,
            'production_unchanged': True,
        })
    return sorted(result, key=lambda x: str(x['feed_id']))


def trends(hours=24):
    """Time-series trend of fetch health from the sampler JSONL.

    Returns per-feed buckets (default hourly over the last `hours` hours)
    with success rate and average latency, plus a list of recent error
    events.  Read-only; production unchanged.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    grouped = defaultdict(list)
    for row in _read():
        ts = row.get('sampled_at')
        try:
            dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        except Exception:
            continue
        if dt < start:
            continue
        grouped[str(row.get('feed_id'))].append({**row, '_dt': dt})
    result = []
    all_errors = []
    for feed_id, rows in grouped.items():
        rows.sort(key=lambda x: x['_dt'])
        buckets = {}
        for r in rows:
            key = r['_dt'].strftime('%Y-%m-%dT%H:00')
            b = buckets.setdefault(key, {'ok': 0, 'total': 0, 'latencies': []})
            b['total'] += 1
            ok = isinstance(r.get('status_code'), int) and 200 <= r['status_code'] < 400 and not r.get('error')
            if ok:
                b['ok'] += 1
            if isinstance(r.get('latency_ms'), (int, float)):
                b['latencies'].append(float(r['latency_ms']))
            if r.get('error'):
                all_errors.append({'feed_id': feed_id, 'sampled_at': r['sampled_at'],
                                   'error': str(r['error'])[:200],
                                   'status_code': r.get('status_code'),
                                   'title': r.get('title') or ''})
        series = []
        for key in sorted(buckets):
            b = buckets[key]
            series.append({
                'bucket': key,
                'success_rate': round(b['ok'] / b['total'], 3) if b['total'] else None,
                'average_latency_ms': round(sum(b['latencies']) / len(b['latencies']), 1) if b['latencies'] else None,
                'samples': b['total'],
            })
        ok_rows = [r for r in rows if isinstance(r.get('status_code'), int) and 200 <= r['status_code'] < 400 and not r.get('error')]
        lat = [float(r['latency_ms']) for r in rows if isinstance(r.get('latency_ms'), (int, float))]
        result.append({
            'feed_id': feed_id,
            'title': rows[-1].get('title') if rows else '',
            'window_hours': hours,
            'samples': len(rows),
            'success_rate': round(len(ok_rows) / len(rows), 3) if rows else None,
            'average_latency_ms': round(sum(lat) / len(lat), 1) if lat else None,
            'p95_latency_ms': _p95(lat),
            'series': series,
            'production_unchanged': True,
        })
    result.sort(key=lambda x: str(x['feed_id']))
    all_errors.sort(key=lambda x: str(x.get('sampled_at') or ''), reverse=True)
    return {'version': 'feed-health-trends-v1', 'production_unchanged': True,
            'window_hours': hours, 'feeds': result,
            'recent_errors': all_errors[:20]}
