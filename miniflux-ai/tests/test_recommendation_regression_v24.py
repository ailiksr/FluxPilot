import json
from pathlib import Path

def recommended(row):
    return round(row['score']*row['feed_weight'],2)

def test_recommendation_order():
    rows=json.loads(Path(__file__).with_name('recommendation_regression_v24.json').read_text())
    ranked=sorted(rows,key=recommended,reverse=True)
    assert [x['id'] for x in ranked]==['p1','p3','p2']

def test_feed_weight_is_secondary():
    a={'score':88,'feed_weight':1}
    b={'score':50,'feed_weight':1.5}
    assert recommended(a)>recommended(b)
