"""V23 scoring regression, confidence and deterministic explainability.

No LLM calls occur here. Judge remains 0..5 integers; this module provides
bounded, dataset-independent calibration plus confidence and an explanation.
"""
from __future__ import annotations
from .score_calibration_v22 import WEIGHTS, PENALTIES
VERSION = "v23"

ANCHORS = ((0.0,10.0),(1.25,30.0),(2.5,50.0),(3.75,70.0),(5.0,90.0))

def _weighted(j): return sum(WEIGHTS[k] * float(j.get(k,0)) for k in WEIGHTS)

def _anchor_score(q):
    if q <= 0: return 10.0
    if q >= 5: return 90.0
    for (x1,y1),(x2,y2) in zip(ANCHORS,ANCHORS[1:]):
        if q <= x2:
            return y1 + (q-x1)*(y2-y1)/(x2-x1)
    return 90.0

def score_breakdown(judge: dict) -> dict:
    q=_weighted(judge)
    base=_anchor_score(q)
    penalties={k: PENALTIES[k]*float(judge.get(k,0)) for k in PENALTIES}
    total=sum(penalties.values())
    empty=all(float(judge.get(k,0))==0 for k in WEIGHTS)
    raw=base-total
    if empty: raw=min(raw,18.0)
    final=max(10.0,min(90.0,raw))
    # Confidence is about Judge signal quality, not article value.
    vals=[float(judge.get(k,0)) for k in WEIGHTS]
    spread=max(vals)-min(vals)
    confidence=0.90 if spread<=2 else 0.82 if spread<=3 else 0.72
    if empty: confidence=0.60
    return {'quality':round(q,4),'base_score':round(base,2),
            'penalties':{k:round(v,2) for k,v in penalties.items()},
            'penalty_total':round(total,2),'raw_score':round(raw,2),
            'score':int(round(final)),'confidence':confidence,
            'score_version':VERSION}

def score(judge): return score_breakdown(judge)['score']
