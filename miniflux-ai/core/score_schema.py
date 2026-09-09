from dataclasses import dataclass
from typing import Any

FIELDS = (
    "value_score", "information_density", "timeliness", "originality", "depth", "relevance"
)

@dataclass(frozen=True)
class ArticleScore:
    value_score: float
    information_density: float
    timeliness: float
    originality: float
    depth: float
    relevance: float
    category: str
    reason: str
    confidence: float


def _num(value: Any, name: str, lo: float = 0, hi: float = 10) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not lo <= n <= hi:
        raise ValueError(f"{name} out of range: {n}")
    return n


def validate_score(data: dict[str, Any]) -> ArticleScore:
    if not isinstance(data, dict):
        raise ValueError("score must be a JSON object")
    missing = [k for k in (*FIELDS, "category", "reason", "confidence") if k not in data]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    return ArticleScore(
        value_score=_num(data["value_score"], "value_score"),
        information_density=_num(data["information_density"], "information_density"),
        timeliness=_num(data["timeliness"], "timeliness"),
        originality=_num(data["originality"], "originality"),
        depth=_num(data["depth"], "depth"),
        relevance=_num(data["relevance"], "relevance"),
        category=str(data["category"]).strip(),
        reason=str(data["reason"]).strip(),
        confidence=_num(data["confidence"], "confidence", 0, 1),
    )
