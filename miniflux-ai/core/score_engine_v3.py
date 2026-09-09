from dataclasses import dataclass
@dataclass(frozen=True)
class JudgeV3:
    new_information:int
    factual_evidence:int
    depth:int
    timeliness:int
    originality:int
    promotional:int
    entertainment_only:int
    low_content:int
    informative_entertainment:int

def score(j:JudgeV3)->int:
    base=(22*j.new_information+18*j.factual_evidence+18*j.depth+10*j.timeliness+12*j.originality)
    if j.informative_entertainment: base+=12
    if j.entertainment_only: base-=22
    if j.promotional: base-=35
    if j.low_content: base-=25
    if j.low_content and not (j.new_information or j.factual_evidence or j.depth): base=min(base,15)
    return max(0,min(100,round(base)))
