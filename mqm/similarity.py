"""各字段的相似度算法。每个函数返回 [0,1]，或 None 表示"这个字段无法比较"。"""

from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np

from .encoders import Encoder
from .structure import StructureSignature

SET_MODES = ("f1", "mean", "overlap", "query_coverage", "query_biased", "jaccard", "lcs")


def cosine_matrix(encoder: Encoder, left: Sequence[str], right: Sequence[str]) -> np.ndarray:
    """(|left|, |right|) 的 cosine 矩阵；字面完全相同的对强制为 1.0。"""
    if not left or not right:
        return np.zeros((len(left), len(right)), dtype=np.float32)
    a = encoder.encode(list(left))
    b = encoder.encode(list(right))
    mat = np.clip(a @ b.T, 0.0, 1.0)
    for i, li in enumerate(left):
        for j, rj in enumerate(right):
            if li == rj:
                mat[i, j] = 1.0
    return mat


def text_similarity(encoder: Encoder, a: Optional[str], b: Optional[str]) -> Optional[float]:
    if not a or not b:
        return None
    if a == b:
        return 1.0
    return float(cosine_matrix(encoder, [a], [b])[0, 0])


def _soft_lcs(mat: np.ndarray, threshold: float = 0.5) -> float:
    """顺序敏感的软最长公共子序列，用于 solution_steps。"""
    n, m = mat.shape
    dp = np.zeros((n + 1, m + 1), dtype=np.float32)
    for i in range(n):
        for j in range(m):
            gain = mat[i, j] if mat[i, j] >= threshold else 0.0
            dp[i + 1, j + 1] = max(dp[i, j] + gain, dp[i, j + 1], dp[i + 1, j])
    return float(dp[n, m] / max(n, m))


def set_similarity(
    encoder: Encoder,
    query: Sequence[str],
    candidate: Sequence[str],
    mode: str = "f1",
    sim_floor: float = 0.0,
) -> Optional[float]:
    """列表字段的软集合相似度。

    先算 query×candidate 的相似度矩阵，然后：
      - query_coverage: query 每个元素找对面最佳匹配后取均值（"query 被覆盖得多好"）
      - overlap:        两个方向取大者（子集包含关系会得高分）
      - mean / f1:      两个方向的算术 / 调和平均，f1 最严格，默认
      - query_biased:   0.7·query_coverage + 0.3·f1，偏向"query 的考点都被覆盖到"
      - jaccard:        不用向量，纯字面集合交并比
      - lcs:            顺序敏感（步骤序列用）
    """
    if not query or not candidate:
        return None
    if mode not in SET_MODES:
        raise ValueError(f"未知 set mode: {mode!r}，支持 {SET_MODES}")

    if mode == "jaccard":
        qs, cs = set(query), set(candidate)
        return len(qs & cs) / len(qs | cs)

    mat = cosine_matrix(encoder, query, candidate)
    if sim_floor > 0.0:
        mat = np.where(mat >= sim_floor, mat, 0.0)

    if mode == "lcs":
        return _soft_lcs(mat)

    cov_q = float(mat.max(axis=1).mean())  # query 侧覆盖度
    cov_c = float(mat.max(axis=0).mean())  # candidate 侧覆盖度

    if mode == "query_coverage":
        return cov_q
    if mode == "overlap":
        return max(cov_q, cov_c)
    if mode == "mean":
        return (cov_q + cov_c) / 2
    f1 = 0.0 if cov_q + cov_c == 0 else 2 * cov_q * cov_c / (cov_q + cov_c)
    if mode == "f1":
        return f1
    return 0.7 * cov_q + 0.3 * f1  # query_biased


def difficulty_similarity(
    query: Optional[float], candidate: Optional[float], scale: float = 5.0
) -> Optional[float]:
    if query is None or candidate is None:
        return None
    if scale <= 0:
        raise ValueError("difficulty.scale 必须为正数")
    return max(0.0, 1.0 - abs(float(query) - float(candidate)) / scale)


def structure_similarity(
    encoder: Encoder,
    query: StructureSignature,
    candidate: StructureSignature,
    type_w: float = 0.5,
    form_w: float = 0.35,
    varcount_w: float = 0.15,
) -> Optional[float]:
    """type + 归一化形式 + 变量个数 三部分加权；缺失的部分权重重新归一。"""
    if query.is_empty or candidate.is_empty:
        return None

    parts: List[tuple[float, float]] = []  # (weight, score)

    qt, ct = query.effective_type, candidate.effective_type
    if qt and ct:
        parts.append((type_w, 1.0 if qt == ct else (text_similarity(encoder, qt, ct) or 0.0)))

    if query.normalized and candidate.normalized:
        if query.normalized == candidate.normalized:
            form = 1.0
        elif query.monomials and candidate.monomials:
            qm, cm = set(query.monomials), set(candidate.monomials)
            form = len(qm & cm) / len(qm | cm)
        else:
            form = text_similarity(encoder, query.normalized, candidate.normalized) or 0.0
        parts.append((form_w, form))
    elif query.monomials and candidate.monomials:
        qm, cm = set(query.monomials), set(candidate.monomials)
        parts.append((form_w, len(qm & cm) / len(qm | cm)))

    qv, cv = query.variable_count, candidate.variable_count
    if qv is not None and cv is not None:
        parts.append((varcount_w, 1.0 - abs(qv - cv) / max(1, qv, cv)))

    total_w = sum(w for w, _ in parts)
    if total_w <= 0:
        return None
    return sum(w * s for w, s in parts) / total_w
