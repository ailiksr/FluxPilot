import importlib.util, pathlib, sys, types
_pkg=types.ModuleType("core"); _pkg.__path__=[str(pathlib.Path(__file__).parents[1]/"core")]; sys.modules["core"]=_pkg
_spec=importlib.util.spec_from_file_location("core.score_calibration_v23", pathlib.Path(__file__).parents[1]/"core/score_calibration_v23.py")
_mod=importlib.util.module_from_spec(_spec); sys.modules["core.score_calibration_v23"]=_mod; _spec.loader.exec_module(_mod)
score, score_breakdown = _mod.score, _mod.score_breakdown
F=("information","evidence","depth","timeliness","originality","practicality")
def j(v=0,**x):
 d={k:v for k in F}; d.update(promotional=0,entertainment_only=0,low_content=0); d.update(x); return d
def test_anchors():
 assert score(j(0))==10 and score(j(1.25))==30 and score(j(2.5))==50 and score(j(3.75))==70 and score(j(5))==90
def test_monotonic(): assert [score(j(v)) for v in range(6)]==sorted(score(j(v)) for v in range(6))
def test_soft_penalty():
 b=score(j(3)); assert score(j(3,promotional=5))<b and score(j(3,low_content=5))<b
def test_empty_floor(): assert score(j(0,low_content=5))==10
def test_confidence_and_explanation():
 b=score_breakdown(j(3,promotional=2)); assert b['score_version']=='v23' and b['confidence']>=.8 and b['penalty_total']==1.2
