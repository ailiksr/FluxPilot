import json
from pathlib import Path

def test_fixture_integrity():
    d=json.loads(Path(__file__).with_name('real_article_benchmark_v24.json').read_text())
    assert len(d['items']) >= 3
    for x in d['items']:
        assert x['title'] and x['judge_hash'] and len(x['judge']) >= 9
