"""题库索引：召回 -> 字段级重排。另附整份 JSON 的 KNN baseline 用于对照。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import numpy as np

from .encoders import Encoder, get_encoder
from .schema import Question, load_aliases
from .scoring import ScoreResult, score_pair

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.json"


def load_config(path: str | Path | None = None) -> Dict:
    """读 config；未指定则用项目自带的 config/default.json。"""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    config = json.loads(p.read_text(encoding="utf-8"))
    alias_path = config.get("aliases_path")
    if alias_path and not Path(alias_path).is_absolute():
        config["aliases_path"] = str((p.parent.parent / alias_path).resolve())
    return config


def aliases_from_config(config: Dict) -> Dict[str, Dict[str, str]]:
    return load_aliases(config.get("aliases_path"))


def match_defaults(config: Dict) -> Dict[str, float]:
    """检索阈值和默认条数：低于 min_score 的结果直接不要（挡掉跨科目的凑数题）。"""
    cfg = config.get("match", {}) or {}
    return {
        "min_score": max(0.0, min(1.0, float(cfg.get("min_score", 0.0)))),
        "topk": int(cfg.get("topk", 5)),
    }


@dataclass
class Match:
    qid: str
    score: float
    result: ScoreResult
    question: Question
    recall_reason: str = ""

    @property
    def breakdown(self) -> Dict[str, float]:
        return self.result.breakdown

    def to_dict(self) -> Dict:
        return {
            "id": self.qid,
            "score": round(self.score, 4),
            "breakdown": self.breakdown,
            "skipped_fields": self.result.skipped,
            "weight_covered": round(self.result.weight_covered, 3),
            "recall": self.recall_reason,
        }


@dataclass
class QuestionIndex:
    questions: List[Question]
    encoder: Encoder = None  # type: ignore[assignment]
    config: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.encoder is None:
            self.encoder = get_encoder(self.config.get("encoder", "hashing"))
        self._by_id = {q.qid: q for q in self.questions}
        self._inverted: Dict[str, Set[str]] = {}
        for q in self.questions:
            for token in list(q.knowledge_points) + list(q.method):
                self._inverted.setdefault(token, set()).add(q.qid)
        docs = [q.knn_document() for q in self.questions]
        self._doc_vectors = (
            self.encoder.encode(docs) if docs else np.zeros((0, self.encoder.dim), dtype=np.float32)
        )

    # ---------- 召回 ----------

    def recall(self, query: Question) -> Dict[str, str]:
        """返回 {qid: 召回原因}。倒排命中 + 向量粗筛，池子太小就补全库。"""
        cfg = self.config.get("recall", {})
        reasons: Dict[str, str] = {}

        if cfg.get("use_inverted_index", True):
            for token in list(query.knowledge_points) + list(query.method):
                for qid in self._inverted.get(token, ()):  # 字面命中考点/考法
                    reasons.setdefault(qid, f"inverted:{token}")

        knn_k = int(cfg.get("knn_prefilter", 50))
        if knn_k > 0 and len(self.questions):
            for qid, _ in self.knn(query, topk=knn_k):
                reasons.setdefault(qid, "knn")

        min_pool = int(cfg.get("min_pool", 20))
        if len(reasons) < min(min_pool, len(self.questions)):
            for q in self.questions:
                reasons.setdefault(q.qid, "fallback:all")
        return reasons

    # ---------- 主流程 ----------

    def match(
        self, query: Question, topk: int = 5, min_score: float = 0.0, rescore_all: bool = False
    ) -> List[Match]:
        pool = (
            {q.qid: "all" for q in self.questions} if rescore_all else self.recall(query)
        )
        matches: List[Match] = []
        for qid, reason in pool.items():
            candidate = self._by_id[qid]
            if candidate.qid == query.qid:
                continue  # 自己不和自己比
            result = score_pair(query, candidate, self.encoder, self.config)
            if result.total < min_score:
                continue
            matches.append(
                Match(
                    qid=qid,
                    score=result.total,
                    result=result,
                    question=candidate,
                    recall_reason=reason,
                )
            )
        matches.sort(key=lambda m: (-m.score, m.qid))
        return matches[:topk] if topk else matches

    # ---------- baseline ----------

    def knn(self, query: Question, topk: int = 5) -> List[tuple[str, float]]:
        """整份 JSON 拍平成一个 embedding 后的 cosine KNN —— 对照组，不是主路径。"""
        if not len(self._doc_vectors):
            return []
        vec = self.encoder.encode([query.knn_document()])[0]
        sims = np.clip(self._doc_vectors @ vec, -1.0, 1.0)
        order = np.argsort(-sims)
        out: List[tuple[str, float]] = []
        for idx in order:
            q = self.questions[int(idx)]
            if q.qid == query.qid:
                continue
            out.append((q.qid, float(sims[int(idx)])))
            if topk and len(out) >= topk:
                break
        return out

    # ---------- 杂项 ----------

    def get(self, qid: str) -> Optional[Question]:
        return self._by_id.get(qid)

    def __len__(self) -> int:
        return len(self.questions)


def build_index(
    questions: Sequence[Question],
    config: Optional[Dict] = None,
    encoder_spec: Optional[str] = None,
) -> QuestionIndex:
    config = dict(config or {})
    if encoder_spec:
        config["encoder"] = encoder_spec
    return QuestionIndex(list(questions), config=config)
