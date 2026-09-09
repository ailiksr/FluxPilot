import json
from pathlib import Path

def test_candidate_pool_schema():
 d=json.loads(Path('tests/real_article_candidate_pool_v24.json').read_text())
 assert isinstance(d['items'],list)
 for x in d['items']:
  assert 'entry_id' in x
  assert 'human_review' in x
  assert x['human_review']['status']=='pending'
