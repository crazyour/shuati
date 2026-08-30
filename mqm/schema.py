"""题目 JSON 的加载、别名归一与校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .structure import StructureSignature, parse_structure

LIST_FIELDS = ("knowledge_points", "method", "solution_steps")
ALL_FIELDS = LIST_FIELDS + ("question_type", "math_structure", "difficulty")

_ALIAS_NAMESPACES = ("knowledge_points", "method", "question_type")


@dataclass
class Question:
    qid: str
    knowledge_points: List[str] = field(default_factory=list)
    question_type: Optional[str] = None
    method: List[str] = field(default_factory=list)
    solution_steps: List[str] = field(default_factory=list)
    math_structure: StructureSignature = field(default_factory=StructureSignature)
    difficulty: Optional[float] = None
    text: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def knn_document(self) -> str:
        """整份 JSON 拍平成一段文本，只给 KNN baseline 用。"""
        chunks = [
            " ".join(self.knowledge_points),
            self.question_type or "",
            " ".join(self.method),
            " ".join(self.solution_steps),
            self.math_structure.template or self.math_structure.effective_type or "",
            "" if self.difficulty is None else f"difficulty {self.difficulty:g}",
            self.text or "",
        ]
        return " | ".join(c for c in chunks if c)

    def present_fields(self) -> List[str]:
        out = []
        for name in ALL_FIELDS:
            value = getattr(self, name)
            if name == "math_structure":
                if not value.is_empty:
                    out.append(name)
            elif isinstance(value, list):
                if value:
                    out.append(name)
            elif value is not None:
                out.append(name)
        return out


def _as_list(value: Any, field_name: str, qid: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(v).strip() for v in value if str(v).strip()]
    raise TypeError(f"[{qid}] {field_name} 应为字符串数组，得到 {type(value)!r}")


def _apply_aliases(items: Sequence[str], table: Dict[str, str]) -> List[str]:
    """归一后去重，保持原顺序。"""
    seen: Dict[str, None] = {}
    for item in items:
        seen.setdefault(table.get(item, item), None)
    return list(seen)


def question_from_dict(
    data: Dict[str, Any],
    aliases: Optional[Dict[str, Dict[str, str]]] = None,
    default_id: str = "query",
) -> Question:
    aliases = aliases or {}
    qid = str(data.get("id") or data.get("qid") or default_id)

    lists = {
        name: _as_list(data.get(name), name, qid)
        for name in LIST_FIELDS
    }
    for name in _ALIAS_NAMESPACES:
        if name in lists:
            lists[name] = _apply_aliases(lists[name], aliases.get(name, {}))

    qtype = data.get("question_type")
    if qtype is not None:
        qtype = str(qtype).strip() or None
    if qtype:
        qtype = aliases.get("question_type", {}).get(qtype, qtype)

    difficulty = data.get("difficulty")
    if difficulty is not None:
        try:
            difficulty = float(difficulty)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"[{qid}] difficulty 应为数字，得到 {difficulty!r}") from exc

    return Question(
        qid=qid,
        knowledge_points=lists["knowledge_points"],
        question_type=qtype,
        method=lists["method"],
        solution_steps=lists["solution_steps"],
        math_structure=parse_structure(data.get("math_structure")),
        difficulty=difficulty,
        text=data.get("text"),
        raw=data,
    )


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_aliases(path: str | Path | None) -> Dict[str, Dict[str, str]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    data = _read_json(p)
    return {ns: dict(table) for ns, table in data.items()}


def load_questions(
    path: str | Path, aliases: Optional[Dict[str, Dict[str, str]]] = None
) -> List[Question]:
    """题库文件：JSON 数组、{"questions": [...]}，或 JSONL 每行一题。"""
    p = Path(path)
    if p.suffix == ".jsonl":
        records = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        data = _read_json(p)
        if isinstance(data, dict):
            records = data["questions"] if "questions" in data else [data]
        else:
            records = data

    questions = [
        question_from_dict(rec, aliases, default_id=f"q-{i:04d}")
        for i, rec in enumerate(records)
    ]
    seen = set()
    for q in questions:
        if q.qid in seen:
            raise ValueError(f"题库中存在重复 id: {q.qid}")
        seen.add(q.qid)
    return questions


def load_question(
    path: str | Path, aliases: Optional[Dict[str, Dict[str, str]]] = None
) -> Question:
    return question_from_dict(_read_json(path), aliases, default_id="query")
