import json
from pathlib import Path
import importlib.util, pathlib, sys, types
_pkg=types.ModuleType("core"); _pkg.__path__=[str(pathlib.Path(__file__).parents[1]/"core")]; sys.modules["core"]=_pkg
_spec=importlib.util.spec_from_file_location("core.score_calibration_v23", pathlib.Path(__file__).parents[1]/"core/score_calibration_v23.py")
_mod=importlib.util.module_from_spec(_spec); sys.modules["core.score_calibration_v23"]=_mod; _spec.loader.exec_module(_mod)
score = _mod.score

def test_semantic_benchmark_ranges():
    data=json.loads(Path(__file__).with_name('score_benchmark_v24.json').read_text())
    for row in data:
        got=score(row['judge']); lo,hi=row['range']
        assert lo <= got <= hi, f"{row['id']} expected {lo}-{hi}, got {got}"

def test_rank_order():
    data=json.loads(Path(__file__).with_name('score_benchmark_v24.json').read_text())
    vals=[score(x['judge']) for x in data]
    assert vals == sorted(vals)

def test_extremes_are_not_common():
    data=json.loads(Path(__file__).with_name('score_benchmark_v24.json').read_text())
    vals=[score(x['judge']) for x in data]
    assert sum(v<=10 for v in vals) <= 1
    assert sum(v>=90 for v in vals) <= 1
