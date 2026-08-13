"""文本编码器。默认离线可跑，可替换成任意向量服务。"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Protocol, Sequence

import numpy as np

_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_WS_RE = re.compile(r"\s+")


class Encoder(Protocol):
    """实现这两个成员即可接入：encode 返回 L2 归一化的 (n, dim) 矩阵。"""

    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return mat / norms


class HashingEncoder:
    """字符 n-gram 的 signed hashing。无需下载模型，结果确定可复现。

    中文按 1~3 字滑窗，拉丁词整词额外算一维，所以 "二次函数" 和 "二次函数图象"
    会有相当高的 cosine，而 "求最值" 和 "解方程" 很低。它是**字面**相似度，
    真正需要语义泛化时换成 sbert:*。
    """

    def __init__(self, dim: int = 1024, ngram_min: int = 1, ngram_max: int = 3):
        self.dim = dim
        self.ngram_min = ngram_min
        self.ngram_max = ngram_max

    def _features(self, text: str) -> List[str]:
        compact = _WS_RE.sub("", text).lower()
        feats: List[str] = []
        for n in range(self.ngram_min, self.ngram_max + 1):
            for i in range(len(compact) - n + 1):
                feats.append(compact[i : i + n])
        feats.extend(f"w:{w}" for w in _LATIN_RE.findall(compact))
        return feats

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feat in self._features(text):
                digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
                slot = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                out[row, slot] += sign
        return _l2_normalize(out)


class SentenceTransformerEncoder:
    """sentence-transformers 包装。中文推荐 BAAI/bge-small-zh-v1.5。"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", device: str | None = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - 依赖可选
            raise ImportError(
                "需要 sentence-transformers：pip install sentence-transformers"
            ) from exc
        self.model_name = model_name
        self._model = SentenceTransformer(model_name, device=device)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self._model.encode(
            list(texts), normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vecs, dtype=np.float32)


class CachedEncoder:
    """按文本去重 + 缓存。字段级打分会反复编码同一批短词，这层很值。"""

    def __init__(self, base: Encoder):
        self.base = base
        self.dim = base.dim
        self._cache: Dict[str, np.ndarray] = {}

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            vecs = self.base.encode(missing)
            for text, vec in zip(missing, vecs):
                self._cache[text] = vec
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._cache[t] for t in texts])


def get_encoder(spec: str = "hashing") -> Encoder:
    """spec: "hashing" | "hashing:<dim>" | "sbert:<model_name>" """
    if spec.startswith("sbert:"):
        return CachedEncoder(SentenceTransformerEncoder(spec.split(":", 1)[1]))
    if spec == "sbert":
        return CachedEncoder(SentenceTransformerEncoder())
    if spec.startswith("hashing:"):
        return CachedEncoder(HashingEncoder(dim=int(spec.split(":", 1)[1])))
    if spec == "hashing":
        return CachedEncoder(HashingEncoder())
    raise ValueError(f"未知 encoder: {spec!r}（支持 hashing / hashing:<dim> / sbert:<model>）")
