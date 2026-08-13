"""命令行：图片 -> 题目 JSON。

    python -m pipeline.cli --image 题目.png                 # 打印 JSON
    python -m pipeline.cli --image 题目.png --out q.json    # 存文件，接着喂给 mqm.cli match
    python -m pipeline.cli --text "已知 y=x2-4x+7，求最小值"  # 跳过 OCR，只调模型
    python -m pipeline.cli --image 题目.png --ocr-only       # 只看 OCR 结果，不调模型
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mqm import aliases_from_config, load_config  # noqa: E402

from .extract import extract_from_image, extract_from_text  # noqa: E402
from .llm import LLMConfig, LLMError  # noqa: E402
from .ocr import DEFAULT_LANGUAGES, OcrError, available_backends, ocr_image  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="图片/文本 -> 题目 JSON（OCR + MiniMax）")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", help="题目图片")
    source.add_argument("--text", help="已有的题目文本，跳过 OCR")
    parser.add_argument("--out", help="把 JSON 写到文件")
    parser.add_argument("--config", default=None, help="config JSON 路径")
    parser.add_argument("--model", default=None, help="覆盖模型名，如 MiniMax-M2.7-highspeed")
    parser.add_argument("--ocr-backend", dest="ocr_backend", default=None, help="auto | vision | tesseract")
    parser.add_argument("--ocr-only", dest="ocr_only", action="store_true", help="只做 OCR，不调模型")
    parser.add_argument("--verbose", action="store_true", help="打印 OCR 文本和模型原始输出")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if args.ocr_backend:
        config.setdefault("ocr", {})["backend"] = args.ocr_backend
    if args.model:
        config.setdefault("llm", {})["model"] = args.model

    if args.ocr_only:
        if not args.image:
            parser.error("--ocr-only 需要配合 --image")
        try:
            ocr = ocr_image(
                args.image,
                backend=config.get("ocr", {}).get("backend", "auto"),
                languages=tuple(config.get("ocr", {}).get("languages", DEFAULT_LANGUAGES)),
            )
        except OcrError as exc:
            print(f"OCR 失败：{exc}", file=sys.stderr)
            return 1
        conf = "-" if ocr.confidence is None else f"{ocr.confidence:.2f}"
        print(f"[{ocr.backend}] 平均置信度 {conf}\n{ocr.text}")
        return 0

    llm_cfg = LLMConfig.from_config(config)
    if args.verbose:
        print(
            f"OCR 后端候选：{', '.join(available_backends()) or '无'}\n"
            f"模型：{llm_cfg.model} @ {llm_cfg.endpoint}\n",
            file=sys.stderr,
        )

    aliases = aliases_from_config(config)
    try:
        if args.image:
            result = extract_from_image(args.image, config, aliases)
        else:
            result = extract_from_text(args.text, config, aliases)
    except (OcrError, LLMError, ValueError) as exc:
        print(f"提取失败：{exc}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"--- OCR 文本 ---\n{result.ocr_text}\n--- 模型原始输出 ---\n{result.model_output}\n",
              file=sys.stderr)
    for warning in result.warnings:
        print(f"提醒：{warning}", file=sys.stderr)

    payload = json.dumps(result.question_json, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(f"已写入 {args.out}", file=sys.stderr)
    print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
