"""字段级相似度 -> 加权总分。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .encoders import Encoder
from .schema import Question
from .similarity import (
    difficulty_similarity,
    set_similarity,
    structure_similarity,
    text_similarity,
)

DEFAULT_WEIGHTS: Dict[str, float] = {
    "knowledge_points": 0.35,
    "method": 0.35,
    "math_structure": 0.15,
    "question_type": 0.10,
    "difficulty": 0.05,
    "solution_steps": 0.0,
}

# 打分明细里的短标签，用于表格展示
FIELD_LABELS = {
    "knowledge_points": "K",
    "method": "M",
    "math_structure": "S",
    "question_type": "Q",
    "difficulty": "D",
    "solution_steps": "P",
}


@dataclass
class FieldScore:
    field: str
    weight: float
    score: Optional[float]  # None = 该字段无法比较（任一侧缺失）

    @property
    def comparable(self) -> bool:
        return self.score is not None


@dataclass
class ScoreResult:
    total: float
    fields: List[FieldScore]
    skipped: List[str]
    weight_covered: float  # 可比较字段占原始权重之和，用于判断这次打分有多可信

    @property
    def breakdown(self) -> Dict[str, float]:
        return {f.field: round(f.score, 4) for f in self.fields if f.comparable}


def _set_mode(config: Dict, field: str) -> Dict:
    section = config.get("set_similarity", {})
    merged = dict(section.get("default", {}))
    merged.update(section.get(field, {}))
    return merged


def score_pair(
    query: Question, candidate: Question, encoder: Encoder, config: Optional[Dict] = None
) -> ScoreResult:
    """算 Score = Σ wᵢ·simᵢ。任一侧缺失的字段跳过，剩余权重重新归一化。"""
    config = config or {}
    weights = {**DEFAULT_WEIGHTS, **config.get("weights", {})}

    raw: Dict[str, Optional[float]] = {}

    for field in ("knowledge_points", "method", "solution_steps"):
        opts = _set_mode(config, field)
        raw[field] = set_similarity(
            encoder,
            getattr(query, field),
            getattr(candidate, field),
            mode=opts.get("mode", "f1"),
            sim_floor=float(opts.get("sim_floor", 0.0)),
        )

    raw["question_type"] = text_similarity(encoder, query.question_type, candidate.question_type)
    raw["math_structure"] = structure_similarity(
        encoder,
        query.math_structure,
        candidate.math_structure,
        **{k: float(v) for k, v in config.get("structure", {}).items()},
    )
    raw["difficulty"] = difficulty_similarity(
        query.difficulty,
        candidate.difficulty,
        scale=float(config.get("difficulty", {}).get("scale", 5)),
    )

    fields = [
        FieldScore(field=name, weight=weights.get(name, 0.0), score=raw.get(name))
        for name in weights
    ]

    active = [f for f in fields if f.comparable and f.weight > 0]
    total_weight = sum(f.weight for f in active)
    total = (
        sum(f.weight * float(f.score) for f in active) / total_weight if total_weight > 0 else 0.0
    )

    weighted_universe = sum(w for w in weights.values() if w > 0) or 1.0
    return ScoreResult(
        total=total,
        fields=fields,
        skipped=[f.field for f in fields if not f.comparable and f.weight > 0],
        weight_covered=total_weight / weighted_universe,
    )
