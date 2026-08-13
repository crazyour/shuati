"""网页服务：贴一道题的 JSON，返回匹配到的题目。

启动：
    python -m webapp.server                     # http://127.0.0.1:8000
    python -m webapp.server --db 我的题库.json --port 9000
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # 允许 python webapp/server.py 直接跑
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify, render_template, request  # noqa: E402

from mqm import (  # noqa: E402
    QuestionIndex,
    Question,
    aliases_from_config,
    load_config,
    load_questions,
    question_from_dict,
)

DEFAULT_DB = ROOT / "data" / "questions.sample.json"
EXAMPLE_QUERY = ROOT / "examples" / "my_question.json"

# 题库里"题目原文"可能用的键名，按顺序取第一个非空的
TEXT_KEYS = ("text", "stem", "question", "content", "题目", "题干")

MAX_TOPK = 50
MAX_UPLOAD_BYTES = 16 * 1024 * 1024
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".gif", ".bmp", ".tiff"}


def question_text(q: Question) -> str:
    """结果只显示题目，所以要尽量找到题目原文；实在没有就用考点凑一句。"""
    for key in TEXT_KEYS:
        value = q.raw.get(key)
        if value and str(value).strip():
            return str(value).strip()
    parts = [p for p in ["、".join(q.knowledge_points), q.question_type] if p]
    return "（该题未提供题目原文）" + ("：" + " / ".join(parts) if parts else f" {q.qid}")


def create_app(
    db_path: Path = DEFAULT_DB,
    config_path: Optional[Path] = None,
    encoder_spec: Optional[str] = None,
) -> Flask:
    config = load_config(config_path)
    if encoder_spec:
        config["encoder"] = encoder_spec
    aliases = aliases_from_config(config)
    index = QuestionIndex(load_questions(db_path, aliases), config=config)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    example = EXAMPLE_QUERY.read_text(encoding="utf-8") if EXAMPLE_QUERY.exists() else "{}"

    def run_match(query: Question, topk: Any) -> Dict[str, Any]:
        try:
            topk = max(1, min(MAX_TOPK, int(topk)))
        except (TypeError, ValueError):
            topk = 5
        matches = index.match(query, topk=topk)
        return {
            "matches": [{"text": question_text(m.question)} for m in matches],
            "db_size": len(index),
        }

    @app.get("/")
    def home():
        from pipeline import available_backends  # 延迟导入：没装 OCR 也要能开页面

        return render_template(
            "index.html",
            db_name=Path(db_path).name,
            db_size=len(index),
            example=example,
            ocr_ready=bool(available_backends()),
            model_name=config.get("llm", {}).get("model", "MiniMax-M2.7"),
        )

    @app.post("/api/match")
    def api_match():
        payload = request.get_json(silent=True) or {}
        raw_query = payload.get("query")

        if isinstance(raw_query, str):
            try:
                raw_query = json.loads(raw_query)
            except json.JSONDecodeError as exc:
                return jsonify({"error": f"JSON 格式有误：{exc.msg}（第 {exc.lineno} 行）"}), 400
        if not isinstance(raw_query, dict):
            return jsonify({"error": "请贴入一道题的 JSON 对象。"}), 400

        try:
            query = question_from_dict(raw_query, aliases, default_id="__web_query__")
        except (TypeError, ValueError) as exc:
            return jsonify({"error": f"题目字段有问题：{exc}"}), 400

        if not query.present_fields():
            return jsonify({"error": "这道题一个可比较的字段都没有，至少要填 knowledge_points 或 method。"}), 400

        return jsonify(run_match(query, payload.get("topk", 5)))

    @app.post("/api/match-image")
    def api_match_image():
        """图片 -> OCR -> MiniMax -> 题目 JSON -> 匹配。"""
        from pipeline import LLMError, MissingAPIKeyError, OcrError, extract_from_image

        upload = request.files.get("image")
        if upload is None or not upload.filename:
            return jsonify({"error": "没有收到图片。"}), 400

        suffix = Path(upload.filename).suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            return jsonify({
                "error": f"不支持的图片格式 {suffix or '(无后缀)'}，"
                         f"支持：{'、'.join(sorted(s.lstrip('.') for s in ALLOWED_IMAGE_SUFFIXES))}"
            }), 400

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            upload.save(tmp.name)
            try:
                extracted = extract_from_image(tmp.name, config, aliases)
            except MissingAPIKeyError as exc:
                return jsonify({"error": str(exc)}), 503
            except (OcrError, LLMError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 502

        body = run_match(extracted.question, request.form.get("topk", 5))
        body.update({
            "ocr_text": extracted.ocr_text,
            "ocr_backend": extracted.ocr_backend,
            "question_json": extracted.question_json,
            "warnings": extracted.warnings,
        })
        return jsonify(body)

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": f"图片太大了，上限 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB。"}), 413

    return app


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="math-question-matcher 网页版")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="题库 JSON / JSONL")
    parser.add_argument("--config", default=None, help="config JSON 路径")
    parser.add_argument("--encoder", default=None, help="hashing | hashing:<dim> | sbert:<model>")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    app = create_app(Path(args.db), args.config, args.encoder)
    print(f"题库：{args.db}\n打开 http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
