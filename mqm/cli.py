"""命令行入口：python -m mqm.cli match|compare|inspect --help"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .index import Match, QuestionIndex, aliases_from_config, load_config, match_defaults
from .library import DATA_ROOT, group_by_source, list_subjects, load_scope, subject_files
from .schema import Question, load_question, load_questions
from .scoring import DEFAULT_WEIGHTS, FIELD_LABELS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "questions.sample.json"


_WIDE_EXTRA = {"…", "—", "‘", "’", "“", "”"}  # CJK 字体下按两列渲染的标点
ID_WIDTH = 24  # 表格里 id 列的宽度，题库 id 常常挺长


def _char_width(ch: str) -> int:
    return 2 if ord(ch) > 0x2E7F or ch in _WIDE_EXTRA else 1


def _display_width(text: str) -> int:
    """CJK 按两列宽算，表格才不会歪。"""
    return sum(_char_width(ch) for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def _clip(text: str, limit: int) -> str:
    """按显示宽度截断，超出加省略号；表格里所有列都用它。"""
    if _display_width(text) <= limit:
        return text
    chars: List[str] = []
    used = 0
    for ch in text:
        w = _char_width(ch)
        if used + w > limit - 2:  # 给省略号留两列
            chars.append("…")
            break
        chars.append(ch)
        used += w
    return "".join(chars)


def _snippet(q: Question, limit: int = 34) -> str:
    """题目原文压成一行：题目里有换行和 $...$ 公式，直接塞进表格会撑歪。"""
    text = q.text or " / ".join(q.knowledge_points) or q.qid
    return _clip(" ".join(text.replace("$", " ").split()), limit)


def _load_query(args, config: Dict, aliases: Dict) -> Question:
    if getattr(args, "image", None):
        from pipeline import extract_from_image  # 延迟导入：不用图片就不需要 OCR / requests

        result = extract_from_image(args.image, config, aliases)
        for warning in result.warnings:
            print(f"提醒：{warning}", file=sys.stderr)
        print(
            f"[{result.ocr_backend}] OCR: {result.ocr_text.replace(chr(10), ' / ')}\n"
            f"提取到的 JSON: {json.dumps(result.question_json, ensure_ascii=False)}\n",
            file=sys.stderr,
        )
        return result.question
    return load_question(args.query, aliases)


def _build(args) -> tuple[QuestionIndex, Question, Dict]:
    config = load_config(args.config)
    if getattr(args, "encoder", None):
        config["encoder"] = args.encoder
    if getattr(args, "weights", None):
        config["weights"] = {**DEFAULT_WEIGHTS, **json.loads(args.weights)}
    aliases = aliases_from_config(config)
    subject = getattr(args, "subject", None)
    if subject:  # 只在这个范围里找：科目，或「科目/来源」
        questions = load_scope(subject, aliases, getattr(args, "data_root", None) or DATA_ROOT)
    else:
        questions = load_questions(args.db, aliases)
    return QuestionIndex(questions, config=config), _load_query(args, config, aliases), config


def _print_matches(matches: List[Match], explain: bool, min_score: float = 0.0) -> None:
    if not matches:
        print(
            f"没有分数 ≥ {min_score:g} 的题目：要么范围选错了，要么用 --min-score 调低阈值。"
            if min_score else "没有命中任何题目。"
        )
        return

    active = [f for f in matches[0].result.fields if f.weight > 0]
    header = f"{'#':>2}  {_pad('id', ID_WIDTH)}{'score':>7}  "
    if explain:
        header += "".join(f"{FIELD_LABELS.get(f.field, f.field[:2]):>6}" for f in active) + "  "
    header += f"{_pad('题目', 36)}召回"
    print(header)
    print("-" * (_display_width(header) + 2))

    for rank, m in enumerate(matches, 1):
        row = f"{rank:>2}  {_pad(_clip(m.qid, ID_WIDTH - 1), ID_WIDTH)}{m.score:>7.3f}  "
        if explain:
            scores = {f.field: f.score for f in m.result.fields}
            row += "".join(
                f"{'-' if scores.get(f.field) is None else f'{scores[f.field]:.2f}':>6}"
                for f in active
            ) + "  "
        row += f"{_pad(_snippet(m.question), 36)}{m.recall_reason}"
        print(row)

    if explain:
        legend = "  ".join(
            f"{FIELD_LABELS.get(f.field, f.field)}={f.field}(w={f.weight:g})" for f in active
        )
        print(f"\n权重: {legend}")
        skipped = matches[0].result.skipped
        if skipped:
            print(f"本次跳过的字段(权重已重新归一): {', '.join(skipped)}")


def cmd_match(args) -> int:
    index, query, config = _build(args)
    min_score = match_defaults(config)["min_score"] if args.min_score is None else args.min_score
    matches = index.match(
        query, topk=args.topk, min_score=min_score, rescore_all=args.rescore_all
    )
    if args.json:
        print(
            json.dumps(
                {
                    "query": query.qid,
                    "db_size": len(index),
                    "min_score": min_score,
                    "matches": [m.to_dict() for m in matches],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    scope = f"范围: {args.subject}" if args.subject else f"题库: {Path(args.db).name}"
    print(f"query: {query.qid}    {scope}({len(index)} 题)    "
          f"阈值: {min_score:g}    encoder: {index.config.get('encoder')}\n")
    _print_matches(matches, args.explain, min_score)
    if args.baseline:
        print("\n[baseline] 整份 JSON embedding 后的 cosine KNN：")
        for rank, (qid, sim) in enumerate(index.knn(query, topk=args.topk), 1):
            q = index.get(qid)
            print(f"{rank:>2}  {_pad(_clip(qid, ID_WIDTH - 1), ID_WIDTH)}{sim:>7.3f}  {_snippet(q)}")
    return 0


def cmd_compare(args) -> int:
    """字段级打分 vs 整份 JSON KNN，并排看两者的分歧。"""
    index, query, _ = _build(args)
    field_rank = index.match(query, topk=args.topk, rescore_all=True)
    knn_rank = index.knn(query, topk=args.topk)

    print(f"query: {query.qid}    题库: {len(index)} 题\n")
    left_title, right_title = "字段级加权打分", "整份 JSON KNN(baseline)"
    print(f"{'#':>2}  {_pad(left_title, 46)}{right_title}")
    print("-" * 80)
    for i in range(max(len(field_rank), len(knn_rank))):
        left = ""
        if i < len(field_rank):
            m = field_rank[i]
            left = f"{_clip(m.qid, 16)} {m.score:.3f}  {_snippet(m.question, 24)}"
        right = ""
        if i < len(knn_rank):
            qid, sim = knn_rank[i]
            right = f"{_clip(qid, 16)} {sim:.3f}  {_snippet(index.get(qid), 24)}"
        print(f"{i + 1:>2}  {_pad(left, 46)}{right}")

    field_order = [m.qid for m in field_rank]
    knn_order = [qid for qid, _ in knn_rank]
    moved = [qid for qid in knn_order if qid in field_order and knn_order.index(qid) != field_order.index(qid)]
    if moved:
        print(f"\n两种排序位次不同的题: {', '.join(moved)}")
        print("典型分歧：文字/公式很像但问法不同的题会被 KNN 抬高，被字段级打分压下去。")
    return 0


def cmd_inspect(args) -> int:
    """看一道题被解析成什么样，主要用来调结构归一化和别名表。"""
    config = load_config(args.config)
    aliases = aliases_from_config(config)
    q = _load_query(args, config, aliases)
    s = q.math_structure
    print(json.dumps({
        "id": q.qid,
        "knowledge_points(归一后)": q.knowledge_points,
        "question_type(归一后)": q.question_type,
        "method(归一后)": q.method,
        "solution_steps": q.solution_steps,
        "difficulty": q.difficulty,
        "math_structure": {
            "raw_type": s.raw_type,
            "effective_type": s.effective_type,
            "template": s.template,
            "normalized": s.normalized,
            "monomials": list(s.monomials),
            "variables": list(s.variables),
            "variable_count": s.variable_count,
            "degree": s.degree,
            "functions": list(s.functions),
        },
        "可比较字段": q.present_fields(),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_subjects(args) -> int:
    """列出可选的检索范围：data/ 下的科目，以及每个科目里的来源（学校 / 文件）。"""
    root = Path(args.data_root) if args.data_root else DATA_ROOT
    names = list_subjects(root)
    if not names:
        print(f"{root} 下没有科目目录（放一个 data/<科目>/xxx.json 就有了）。")
        return 0

    aliases = aliases_from_config(load_config(args.config))
    print(f"科目根目录: {root}\n")
    print(f"{_pad('--subject 的取值', 30)}{'题数':>6}  说明")
    print("-" * 58)
    print(f"{_pad('__all__', 30)}{'':>6}  整个 data 目录")
    for name in names:
        try:
            sources = group_by_source(subject_files(name, root), aliases, root)
        except (OSError, ValueError, TypeError) as exc:
            print(f"{_pad(name, 30)}{'失败':>6}  {exc}")
            continue
        total = sum(len(qs) for qs in sources.values())
        print(f"{_pad(name, 30)}{total:>6}  科目全部（{len(sources)} 个来源）")
        for source, questions in sources.items():
            print(f"{_pad(f'{name}/{source}', 30)}{len(questions):>6}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mqm.cli", description="字段级加权的数学题相似检索"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, need_query=True):
        p.add_argument("--config", default=None, help="config JSON 路径（默认 config/default.json）")
        p.add_argument("--db", default=str(DEFAULT_DB), help="题库 JSON / JSONL")
        p.add_argument("--subject", default=None,
                       help="检索范围：__all__ | <科目> | <科目>/<来源>，给了就忽略 --db")
        p.add_argument("--data-root", dest="data_root", default=None,
                       help="科目根目录，默认 data/")
        if need_query:
            source = p.add_mutually_exclusive_group(required=True)
            source.add_argument("--query", help="待匹配题目的 JSON 文件")
            source.add_argument("--image", help="题目图片，先 OCR + MiniMax 转成 JSON 再匹配")
        p.add_argument("--encoder", default=None, help="hashing | hashing:<dim> | sbert:<model>")

    p_match = sub.add_parser("match", help="检索相似题")
    common(p_match)
    p_match.add_argument("--topk", type=int, default=5)
    p_match.add_argument("--min-score", dest="min_score", type=float, default=None,
                         help="检索阈值，低于它的结果不要（默认取 config 的 match.min_score）")
    p_match.add_argument("--explain", action="store_true", help="打印各字段分数明细")
    p_match.add_argument("--baseline", action="store_true", help="额外打印整份 JSON 的 KNN 排序")
    p_match.add_argument("--rescore-all", dest="rescore_all", action="store_true", help="跳过召回，全库精算")
    p_match.add_argument("--weights", default=None, help='覆盖权重，如 \'{"method":0.5}\'')
    p_match.add_argument("--json", action="store_true", help="输出 JSON")
    p_match.set_defaults(func=cmd_match)

    p_cmp = sub.add_parser("compare", help="字段级打分 vs 整份 JSON KNN 并排对比")
    common(p_cmp)
    p_cmp.add_argument("--topk", type=int, default=6)
    p_cmp.add_argument("--weights", default=None)
    p_cmp.set_defaults(func=cmd_compare)

    p_ins = sub.add_parser("inspect", help="查看一道题的解析结果")
    common(p_ins)
    p_ins.set_defaults(func=cmd_inspect)

    p_subj = sub.add_parser("subjects", help="列出可选科目（data/ 下的子目录）")
    p_subj.add_argument("--config", default=None)
    p_subj.add_argument("--data-root", dest="data_root", default=None)
    p_subj.set_defaults(func=cmd_subjects)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:  # 科目名写错、题库读不动之类，不用甩堆栈
        print(f"出错了：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
