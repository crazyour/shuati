#!/usr/bin/env python3
"""Fix Markdown/LaTeX delimiters in generated question JSON files safely."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


VALIDATOR = Path(
    "/Users/btang/.codex/skills/analyze-exam-question-json/scripts/validate_question_json.py"
)

SYSTEM_PROMPT = r"""你是 JSON 数学排版校对器。输入是一个已经完成的题目 JSON 对象。
只修复数学排版，不改变题目、答案、数值、推导、字段、数组顺序或文字含义。

要求：
1. 每个数学表达式必须位于 $...$ 或 $$...$$ 中，同一个 JSON 字符串内闭合。
2. 裸露的下标、上标、等式、矩阵、希腊字母和 Unicode 运算符改成 Markdown LaTeX。
3. 数学环境内使用 \\lambda、\\phi、\\ne、\\le、\\ge、\\times、\\cdot、\\in、\\sum、\\operatorname 等命令。
4. JSON 中 LaTeX 反斜杠正确转义。
5. 只输出一个严格 JSON 对象，不要代码围栏或说明。
"""


def extract_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    start = text.find("{")
    if start < 0:
        raise ValueError("没有返回 JSON 对象")
    value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("返回值不是 JSON 对象")
    return value


def stable_shape(original: dict[str, Any], fixed: dict[str, Any]) -> bool:
    stable_fields = ("id", "school", "year", "subject", "source_pdf", "source_type")
    if set(original) != set(fixed):
        return False
    if any(original.get(key) != fixed.get(key) for key in stable_fields):
        return False
    if len(original.get("answer", [])) != len(fixed.get("answer", [])):
        return False
    if len(original.get("practice_questions", [])) != len(fixed.get("practice_questions", [])):
        return False
    return True


def fix_file(path: Path) -> None:
    current_check = subprocess.run(
        ["python3", str(VALIDATOR), "--allow-extensions", str(path)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if current_check.returncode == 0:
        print(f"SKIP {path}", flush=True)
        return
    original = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(original, ensure_ascii=False, indent=2)
    command = [
        "claude", "-p", "--output-format", "text", "--no-session-persistence",
        "--disable-slash-commands", "--tools", "", "--model", "sonnet",
        "--effort", "low", "--system-prompt", SYSTEM_PROMPT,
    ]
    result = subprocess.run(
        command, input=payload, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=900,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:500])
    fixed = extract_object(result.stdout)
    if not stable_shape(original, fixed):
        raise ValueError("校正结果改变了字段或题目结构，拒绝替换")

    serialized = json.dumps(fixed, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    try:
        checked = subprocess.run(
            ["python3", str(VALIDATOR), "--allow-extensions", str(temp_path)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if checked.returncode != 0:
            raise ValueError(checked.stdout.strip())
        path.write_text(serialized, encoding="utf-8")
        print(f"FIXED {path}", flush=True)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    failures = 0
    for path in args.files:
        try:
            fix_file(path)
        except Exception as exc:
            failures += 1
            print(f"FAILED {path}: {exc}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
