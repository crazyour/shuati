"""串起来：图片 -> OCR -> MiniMax -> 校验过的题目 JSON。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from mqm import Question, question_from_dict

from .llm import LLMConfig, Transport, complete, extract_json_object
from .ocr import DEFAULT_LANGUAGES, OcrResult, clean_question_text, ocr_image
from .prompts import SYSTEM_PROMPT, user_prompt

LIST_FIELDS = ("knowledge_points", "method", "solution_steps")
# 这些字段里至少要有一个，否则这次提取没有匹配价值
SUBSTANTIVE_FIELDS = ("knowledge_points", "method", "question_type", "math_structure")
DIFFICULTY_RANGE = (1, 5)


@dataclass
class ExtractResult:
    ocr_text: str
    question_json: Dict[str, Any]
    question: Question
    ocr_backend: str = ""
    ocr_confidence: Optional[float] = None
    model_output: str = ""
    warnings: List[str] = field(default_factory=list)


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out, seen = [], set()
    for item in value:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def normalize_question_json(
    data: Dict[str, Any], ocr_text: str = "", qid: str = "extracted"
) -> Dict[str, Any]:
    """模型输出不一定规矩：类型纠正、字段裁剪、难度夹紧，顺手把题目原文塞进 text。"""
    out: Dict[str, Any] = {"id": data.get("id") or qid}

    for name in LIST_FIELDS:
        items = _as_str_list(data.get(name))
        if items:
            out[name] = items

    qtype = data.get("question_type")
    if isinstance(qtype, (list, tuple)) and qtype:
        qtype = qtype[0]
    if qtype and str(qtype).strip():
        out["question_type"] = str(qtype).strip()

    structure = data.get("math_structure")
    if isinstance(structure, str) and structure.strip():
        out["math_structure"] = structure.strip()
    elif isinstance(structure, dict):
        cleaned: Dict[str, Any] = {}
        for key in ("type", "template"):
            value = structure.get(key)
            if value and str(value).strip():
                cleaned[key] = str(value).strip()
        count = structure.get("variable_count")
        try:
            if count is not None:
                cleaned["variable_count"] = max(0, int(count))
        except (TypeError, ValueError):
            pass
        if cleaned:
            out["math_structure"] = cleaned

    difficulty = data.get("difficulty")
    try:
        if difficulty is not None:
            lo, hi = DIFFICULTY_RANGE
            out["difficulty"] = max(lo, min(hi, int(round(float(difficulty)))))
    except (TypeError, ValueError):
        pass

    given = data.get("text")
    if given and str(given).strip():
        out["text"] = str(given).strip()  # 模型自己整理过的题面优先
    elif ocr_text.strip():
        out["text"] = clean_question_text(ocr_text)  # 退回 OCR 原文，去掉行首题号
    return out


def _from_ocr_text(
    ocr: OcrResult,
    config: Optional[Dict[str, Any]] = None,
    aliases: Optional[Dict[str, Dict[str, str]]] = None,
    transport: Optional[Transport] = None,
) -> ExtractResult:
    if not ocr.text.strip():
        raise ValueError("OCR 没有识别出任何文字，换一张更清晰的图片试试。")

    llm_cfg = LLMConfig.from_config(config)
    raw = complete(SYSTEM_PROMPT, user_prompt(ocr.text), llm_cfg, transport)
    data = normalize_question_json(extract_json_object(raw), ocr.text)
    question = question_from_dict(data, aliases or {}, default_id="extracted")

    warnings: List[str] = []
    # 只有 difficulty 也算"有字段"，但拿它去匹配毫无意义，所以要求至少有一个实质字段
    if not set(question.present_fields()) & set(SUBSTANTIVE_FIELDS):
        raise ValueError(f"模型没有给出任何可比较的字段。它的原始输出：{raw[:300]}")
    for name in ("knowledge_points", "method", "question_type"):
        if name not in data:
            warnings.append(f"模型没给出 {name}")
    if ocr.confidence is not None and ocr.confidence < 0.3:
        warnings.append("OCR 置信度偏低，建议核对识别出的文本")

    return ExtractResult(
        ocr_text=ocr.text,
        question_json=data,
        question=question,
        ocr_backend=ocr.backend,
        ocr_confidence=ocr.confidence,
        model_output=raw,
        warnings=warnings,
    )


def extract_from_image(
    image_path: str | Path,
    config: Optional[Dict[str, Any]] = None,
    aliases: Optional[Dict[str, Dict[str, str]]] = None,
    transport: Optional[Transport] = None,
) -> ExtractResult:
    ocr_cfg = (config or {}).get("ocr", {})
    ocr = ocr_image(
        image_path,
        backend=ocr_cfg.get("backend", "auto"),
        languages=tuple(ocr_cfg.get("languages", DEFAULT_LANGUAGES)),
    )
    return _from_ocr_text(ocr, config, aliases, transport)


def extract_from_text(
    text: str,
    config: Optional[Dict[str, Any]] = None,
    aliases: Optional[Dict[str, Dict[str, str]]] = None,
    transport: Optional[Transport] = None,
) -> ExtractResult:
    """已经有题目文本（不用 OCR）时走这条，方便调提示词。"""
    lines: Sequence[str] = [line for line in text.splitlines() if line.strip()]
    ocr = OcrResult(text="\n".join(lines), lines=[(line, 1.0) for line in lines], backend="text")
    return _from_ocr_text(ocr, config, aliases, transport)
