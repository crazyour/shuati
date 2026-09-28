#!/usr/bin/env python3
"""重组 data/<科目>/ 下的题库文件：

旧路径：data/<科目>/<学校>/<文件名>.json（一个文件一道题）
新路径：data/<科目>/<学校>/<学院>/<专攻>/<年份>.json（同一年份同专攻的多道题合并到一个数组）

学院 / 专攻从 JSON 的 `subject` 字段拆出（约定：前两段 = 学院_专攻；
第 3 段如果不是题目编号（问1/問3/Q2）则继续附加到专攻）。
题目编号段会被丢弃——避免把同一份题库里「問3」这种编号写到目录名里。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# 视作"题目编号"而非"分类名"的后缀段：含问/問字样的、或纯数字/纯数字+字母
QUESTION_NUMBER_RE = re.compile(r"^[问問問Qq]?\d+[号問問问]?$|^[问問]\d+$")
# 但 "問3" 这种汉字 + 数字也命中（汉字科目不足所以用宽匹配）
JA_QUESTION_NUMBER_RE = re.compile(r"^[问問]\d+$")


def is_question_number(segment: str) -> bool:
    """后缀段看起来像题目编号（問3 / Q1 / 2 等），不算分类。"""
    return bool(QUESTION_NUMBER_RE.match(segment) or JA_QUESTION_NUMBER_RE.match(segment))


def split_subject(subject: str) -> tuple[str, str]:
    """拆 `subject` 字段为 (学院, 专攻)。"""
    parts = subject.split("_") if subject else []
    if not parts:
        return ("未知学院", "未知专攻")
    faculty = parts[0]
    if len(parts) == 1:
        return (faculty, faculty)
    major_parts = [parts[1]]
    for seg in parts[2:]:
        if is_question_number(seg):
            continue
        major_parts.append(seg)
    return (faculty, "_".join(major_parts))


def safe_path_component(name: str) -> str:
    """Windows / macOS 通用的目录名清理。"""
    return name.replace("/", "_").replace("\\", "_").strip() or "未命名"


def collect_inputs(data_root: Path) -> list[Path]:
    """旧结构：data/<科目>/<学校>/*.json（学校下面直接是 JSON 文件，不递归）。"""
    if not data_root.exists():
        return []
    out: list[Path] = []
    for subject_dir in sorted(p for p in data_root.iterdir() if p.is_dir()):
        for school_dir in sorted(p for p in subject_dir.iterdir() if p.is_dir()):
            for path in sorted(school_dir.glob("*.json")):
                out.append(path)
    return out


def plan_migration(paths: list[Path]) -> dict[tuple[str, str, str, str, str], list[Path]]:
    """算出每个旧文件应去的目标桶，返回 {目标路径键: [旧文件列表]}。

    键格式：(科目, 学校, 学院, 专攻, 年份)。
    """
    buckets: dict[tuple[str, str, str, str, str], list[Path]] = defaultdict(list)
    skipped: list[tuple[Path, str]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[跳过] {path}: JSON 解析失败 {exc}", file=sys.stderr)
            continue
        subject = path.parts[-3]                 # data/<科目>/<学校>/<file>
        school = str(data.get("school") or path.parts[-2]).strip()
        year = str(data.get("year") or "未知年份").strip()
        subject_field = str(data.get("subject") or "").strip()
        faculty, major = split_subject(subject_field) if subject_field else (school, "未知专攻")
        key = (subject, school, faculty, major, year)
        buckets[key].append(path)
    if skipped:
        print(f"已跳过 {len(skipped)} 个解析失败文件", file=sys.stderr)
    return buckets


def write_bucket(target_dir: Path, key: tuple[str, str, str, str, str], sources: list[Path]) -> Path:
    """把多个旧 JSON 合并成 `target_dir/<年份>.json` 数组。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{safe_path_component(key[4])}.json"
    merged: list[dict] = []
    for src in sources:
        data = json.loads(src.read_text(encoding="utf-8"))
        if isinstance(data, list):
            merged.extend(data)
        elif isinstance(data, dict):
            merged.append(data)
        else:
            raise TypeError(f"{src} 的顶层不是对象或数组：{type(data).__name__}")
    target_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target_path


def migrate(data_root: Path, dry_run: bool = False, backup_root: Path | None = None) -> int:
    inputs = collect_inputs(data_root)
    if not inputs:
        print(f"在 {data_root} 下没找到旧结构的题库文件。")
        return 0
    buckets = plan_migration(inputs)
    print(f"扫描到 {len(inputs)} 个旧文件，规划成 {len(buckets)} 个新文件。")

    if backup_root and not dry_run:
        for path in inputs:
            target = backup_root / path.relative_to(data_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        print(f"已备份原文件到 {backup_root}")

    written = 0
    for key, sources in sorted(buckets.items()):
        subject, school, faculty, major, year = key
        target_dir = data_root / subject / school / safe_path_component(faculty) / safe_path_component(major)
        target_path = target_dir / f"{safe_path_component(year)}.json"
        names = ", ".join(p.name for p in sources)
        print(f"  {subject}/{school}/{faculty}/{major}/{year}.json  ←  {len(sources)} 题 ({names})")
        if not dry_run:
            write_bucket(target_dir, key, sources)
            written += 1

    if not dry_run:
        # 清理旧目录：学校下面（已重组成 <学院>/<专攻>/...）应该不再有任何文件
        for path in inputs:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        # 旧目录（data/<科目>/<学校>/）若为空，顺手删掉
        for subject_dir in sorted(p for p in data_root.iterdir() if p.is_dir()):
            for school_dir in sorted(p for p in subject_dir.iterdir() if p.is_dir()):
                if not any(school_dir.iterdir()):
                    school_dir.rmdir()
    print(f"\n已写入 {written} 个新文件。" if not dry_run else "\n仅预览，未写入。")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把题库重组为 学校/学院/专攻/年份 目录结构")
    parser.add_argument("--data-root", default=str(PROJECT_ROOT / "data"),
                        help="题库根目录（默认 data/）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不动文件")
    parser.add_argument("--backup", default=None,
                        help="把旧文件备份到这个目录（默认 data.bak/，--dry-run 时无效）")
    args = parser.parse_args(argv)

    data_root = Path(args.data_root).resolve()
    backup_root = (Path(args.backup).resolve() if args.backup
                   else (data_root.parent / f"{data_root.name}.bak"))
    migrate(data_root, dry_run=args.dry_run, backup_root=backup_root if not args.dry_run else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())