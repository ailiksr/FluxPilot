import json
from pathlib import Path

def test_annotation_schema():
    data=json.loads(Path(__file__).with_name('real_article_benchmark_v24.json').read_text())
    items=data if isinstance(data,list) else data.get('items',[])
    assert items
    for item in items:
        review=item.get('human_review',{})
        assert review.get('status') in ('pending','reviewed')
        assert 'final_range' in review
