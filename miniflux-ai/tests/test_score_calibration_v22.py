import importlib.util, pathlib
_spec=importlib.util.spec_from_file_location("score_calibration_v22", pathlib.Path(__file__).parents[1]/"core/score_calibration_v22.py")
_mod=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)
score, score_breakdown = _mod.score, _mod.score_breakdown

FIELDS = ("information","evidence","depth","timeliness","originality","practicality")

def judge(v=0, **extra):
    d={k:v for k in FIELDS}
    d.update({"promotional":0,"entertainment_only":0,"low_content":0})
    d.update(extra)
    return d

def test_anchor_points():
    # Weighted mean at 0, 1.25, 2.5, 3.75, 5 => 10, 30, 50, 70, 90.
    assert score(judge(0)) == 10
    assert score(judge(1.25)) == 30
    assert score(judge(2.5)) == 50
    assert score(judge(3.75)) == 70
    assert score(judge(5)) == 90

def test_empty_content_stays_near_floor():
    assert score(judge(0, low_content=5)) == 10

def test_penalties_are_bounded():
    base=score(judge(3))
    assert 50 <= base <= 65
    assert score(judge(3, promotional=5)) < base
    assert score(judge(3, entertainment_only=5)) < base
    assert score(judge(3, low_content=5)) < base

def test_monotonic_quality():
    vals=[score(judge(v)) for v in range(6)]
    assert vals == sorted(vals)
    assert len(set(vals)) == 6

def test_explainable_breakdown():
    b=score_breakdown(judge(3, promotional=2))
    assert b["score_version"] == "v22"
    assert b["penalty_total"] == 1.2
    assert b["base_score"] > b["score"]
