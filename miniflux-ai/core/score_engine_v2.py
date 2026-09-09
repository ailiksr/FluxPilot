from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Judge:
    new_information: int
    factual_evidence: int
    depth: int
    timeliness: int
    originality: int
    promotional: int
    entertainment_noise: int
    empty_or_low_content: int

def score(j: Judge) -> int:
    positive = (
        25*j.new_information +
        15*j.factual_evidence +
        20*j.depth +
        15*j.timeliness +
        25*j.originality
    )
    penalty = 25*j.promotional + 20*j.entertainment_noise + 25*j.empty_or_low_content
    return max(0, min(100, int(round(positive - penalty))))
