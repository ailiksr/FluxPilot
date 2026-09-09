import json
from pathlib import Path

def test_real_benchmark_integrity():
    data=json.loads(Path(__file__).with_name("real_article_benchmark_v24.json").read_text())
    assert data["schema_version"].startswith("v24")
    assert data["items"]
    ids=set()
    for item in data["items"]:
        assert item["id"] not in ids
        ids.add(item["id"])
        assert len(item.get("judge_hash", "")) > 20
        assert "human_review" in item
        assert item["human_review"]["status"] == "pending"
