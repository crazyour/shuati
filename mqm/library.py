"""按科目 / 学校 / 学院 / 专攻 / 年份 五级组织的题库：

    data/<科目>/<学校>/<学院>/<专攻>/<年份>.json

检索范围（scope）是一个字符串，按层级拼接：

    "__all__"                              全部题目
    "线性代数"                              某个科目
    "线性代数/九州大学"                      科目下的某所学校
    "线性代数/九州大学/理学府"               学校下的某个学院
    "线性代数/九州大学/理学府/数学专攻"       学院下的某个专攻
    "线性代数/九州大学/理学府/数学专攻/2026"  专攻下的某个年份

来源（school）取每道题的 `school` / `学校` / `source` / `来源` 字段，
没写就退回目录层级（学校/学院/专攻）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from .schema import Question, load_questions

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
QUESTION_SUFFIXES = (".json", ".jsonl")
ALL_SUBJECTS = "__all__"  # 特殊科目：整个 data 目录
SOURCE_KEYS = ("school", "学校", "source", "来源")

Aliases = Optional[Dict[str, Dict[str, str]]]

# ---------- 路径类型 ----------
# (subject, school, faculty, major, year)
StructuredPath = Tuple[str, str, str, str, str]


def question_files(directory: str | Path, recursive: bool = True) -> List[Path]:
    """目录下的题库文件，按路径排序（默认含子目录）。"""
    d = Path(directory)
    if not d.is_dir():
        return []
    it = d.rglob("*") if recursive else d.iterdir()
    return sorted(p for p in it if p.is_file() and p.suffix.lower() in QUESTION_SUFFIXES)


def list_subjects(root: str | Path | None = None) -> List[str]:
    """data/下**装着题库文件**的子目录名，按名字排序。"""
    r = _root(root)
    if not r.is_dir():
        return []
    return sorted(d.name for d in r.iterdir() if d.is_dir() and question_files(d))


# ---------- 五级结构：科目 / 学校 / 学院 / 专攻 / 年份 ----------


def structured_files(subject: str, root: str | Path | None = None) -> List[Tuple[StructuredPath, Path]]:
    """某科目下的题库文件，**兼容两种目录布局**：

    - 新结构：`科目/学校/学院/专攻/<年份>.json`（__all__ 时多一段科目 → 5 段）
    - 旧结构：`科目/学校/<file>.json`（__all__ 时多一段科目 → 3 段）

    旧结构下，每个 JSON 文件对应一道题（文件里是单个对象），学院 / 专攻
    从 JSON 的 `subject` 字段拆出（约定 `学院_专攻`），年份读 `year` 字段；
    解析不出来时落到「未分类 / 文件名 / 全部」兜底。
    这样新代码不匹配新结构的老仓库（git HEAD 里残留的 3 级目录）也能正常加载。
    """
    import json

    r = _root(root)
    d = r if subject == ALL_SUBJECTS else r / subject
    if not d.is_dir():
        return []
    out: List[Tuple[StructuredPath, Path]] = []
    expected_new = 5 if subject == ALL_SUBJECTS else 4
    expected_old = 3 if subject == ALL_SUBJECTS else 2
    for path in d.rglob("*.json"):
        if not path.is_file() or path.suffix.lower() not in QUESTION_SUFFIXES:
            continue
        rel_parts = path.relative_to(d).parts
        if len(rel_parts) == expected_new:
            # 新结构：科目/学校/学院/专攻/<年份>.json
            if subject == ALL_SUBJECTS:
                subj, school, faculty, major, fname = rel_parts
            else:
                school, faculty, major, fname = rel_parts
                subj = subject
            year = fname[: -len(".json")] if fname.endswith(".json") else fname
        elif len(rel_parts) == expected_old:
            # 旧结构：科目/学校/<file>.json（一个文件一道题）
            if subject == ALL_SUBJECTS:
                subj, school, fname = rel_parts
            else:
                school, fname = rel_parts
                subj = subject
            faculty, major, year = _infer_old_metadata(path)
        else:
            continue
        out.append(((subj, school, faculty, major, year), path))
    out.sort()
    return out


def _infer_old_metadata(path: Path) -> tuple[str, str, str]:
    """旧结构下从 JSON 内容推 (学院, 专攻, 年份)；读不到就给兜底标签。"""
    import json
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return ("未分类", path.stem, "全部")
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return ("未分类", path.stem, "全部")
    subject_field = str(data.get("subject") or "").strip()
    faculty, major = _split_legacy_subject(subject_field) if subject_field else ("未分类", path.stem)
    year = str(data.get("year") or "全部").strip() or "全部"
    return (faculty, major, year)


def _split_legacy_subject(subject: str) -> tuple[str, str]:
    """把旧结构里的 `subject` 字段拆 (学院, 专攻)；处理 `学院_专攻_课程_問N` 形式。"""
    import re
    parts = subject.split("_")
    if not parts:
        return ("未分类", "未分类")
    faculty = parts[0]
    if len(parts) == 1:
        return (faculty, faculty)
    major_parts = [parts[1]]
    for seg in parts[2:]:
        # 末尾的题目编号段（问1/問3/Q2）跳过
        if re.match(r"^[问問Qq]\d+|^[\d]+[号問問]?$", seg):
            continue
        major_parts.append(seg)
    return (faculty, "_".join(major_parts))


def list_schools(subject: str, root: str | Path | None = None) -> List[str]:
    """某科目下有哪些学校。"""
    seen: set = set()
    for (s, school, *_), _ in structured_files(subject, root):
        seen.add(school)
    return sorted(seen)


def list_faculties(subject: str, school: str, root: str | Path | None = None) -> List[str]:
    """某科目 + 学校下有哪些学院。"""
    seen: set = set()
    for (s, sc, faculty, *_), _ in structured_files(subject, root):
        if sc == school:
            seen.add(faculty)
    return sorted(seen)


def list_majors(subject: str, school: str, faculty: str, root: str | Path | None = None) -> List[str]:
    """某科目 + 学校 + 学院下有哪些专攻。"""
    seen: set = set()
    for (s, sc, fac, major, *_), _ in structured_files(subject, root):
        if sc == school and fac == faculty:
            seen.add(major)
    return sorted(seen)


def list_years(
    subject: str, school: str, faculty: str, major: str, root: str | Path | None = None
) -> List[str]:
    """某科目 + 学校 + 学院 + 专攻下有哪些年份。"""
    seen: set = set()
    for (s, sc, fac, mjr, year), _ in structured_files(subject, root):
        if sc == school and fac == faculty and mjr == major:
            seen.add(year)
    return sorted(seen)


# 向后兼容：旧 API 保留
def list_senkou(
    subject: str, school: str, root: str | Path | None = None,
    faculty: str | None = None,
) -> List[str]:
    """旧 API：在某科目 + 学校下有哪些「专攻」层（最后一层非空的目录名）。

    新结构里专攻是 4 级目录的最后一段，因此当 `faculty` 未指定时返回该学校下
    所有 (学院, 专攻) 组合中的「专攻」；指定 faculty 时只列其下的专攻。
    """
    if faculty is not None:
        return list_majors(subject, school, faculty, root)
    seen: set = set()
    for (s, sc, _fac, mjr, *_), _ in structured_files(subject, root):
        if sc == school:
            seen.add(mjr)
    return sorted(seen)


# 向后兼容：原 subject_files 保留
def subject_files(subject: str, root: str | Path | None = None) -> List[Path]:
    """某科目的题库文件；`__all__` 表示整个数据目录。

    保留此函数供 `group_by_source` / `load_scope` 等旧逻辑使用。
    新数据流请用 `structured_files`。
    """
    r = _root(root)
    return question_files(r if subject == ALL_SUBJECTS else r / subject)


def question_source(q: Question, fallback: str) -> str:
    """一道题的来源：school 之类的字段优先，没有就用文件名。"""
    for key in SOURCE_KEYS:
        value = q.raw.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return fallback


def load_question_files(
    paths: Sequence[str | Path], aliases: Aliases = None, base: str | Path | None = None
) -> List[Question]:
    """把多个题库文件合并成一份题目列表。"""
    return [q for _, q in _load_with_dedup(paths, aliases, base)]


def group_by_source(
    paths: Sequence[str | Path], aliases: Aliases = None, base: str | Path | None = None
) -> Dict[str, List[Question]]:
    """{来源: 题目列表}，来源按名字排序。"""
    groups: Dict[str, List[Question]] = {}
    for path, q in _load_with_dedup(paths, aliases, base):
        groups.setdefault(question_source(q, path.stem), []).append(q)
    return dict(sorted(groups.items()))


def split_scope(scope: str) -> Tuple[str, str, str, str, str]:
    """'科目/学校/学院/专攻/年份' -> 5 元组；不足段补空。"""
    parts = (scope or "").split("/")
    while len(parts) < 5:
        parts.append("")
    return tuple(parts)  # type: ignore[return-value]


def load_scope(scope: str, aliases: Aliases = None, root: str | Path | None = None) -> List[Question]:
    """按检索范围加载题目。范围写错会报错，并把可选项列出来。"""
    r = _root(root)
    subject, school, faculty, major, year = split_scope(scope)
    # 逐层下钻 structured_files；任一层为空就报错并列出可选项
    if school:
        files = [
            p for ((s, sc, fac, mjr, yr), p) in structured_files(subject, r)
            if sc == school
            and (not faculty or fac == faculty)
            and (not major or mjr == major)
            and (not year or yr == year)
        ]
        if not files:
            raise ValueError(f"{scope!r} 下没有题库文件")
        return load_question_files(files, aliases, base=r)

    # 没指定学校：要么全科目的，要么整棵 data
    files = subject_files(subject, r)
    if not files:
        available = "、".join([ALL_SUBJECTS, *list_subjects(r)])
        raise ValueError(f"科目 {subject!r} 下没有题库文件；可选：{available}")
    if not faculty and not major and not year:
        return load_question_files(files, aliases, base=r)
    groups = group_by_source(files, aliases, r)
    if faculty and faculty not in groups:
        raise ValueError(f"科目 {subject!r} 下没有来源 {faculty!r}；可选：{'、'.join(groups)}")
    return groups.get(faculty, []) if faculty else []


def load_subject(subject: str, aliases: Aliases = None, root: str | Path | None = None) -> List[Question]:
    """加载一个科目下的全部题目（`load_scope` 的常用情形）。"""
    return load_scope(subject, aliases, root)


def list_sources(subject: str, aliases: Aliases = None, root: str | Path | None = None) -> List[str]:
    """某科目里有哪些来源（旧格式兼容；新格式用 `list_schools`）。"""
    return list(group_by_source(subject_files(subject, _root(root)), aliases, _root(root)))


def _root(root: str | Path | None) -> Path:
    return Path(root) if root else DATA_ROOT


def _load_with_dedup(
    paths: Sequence[str | Path], aliases: Aliases, base: str | Path | None
) -> Iterator[Tuple[Path, Question]]:
    """逐个文件读，顺带处理跨文件撞 id：给后来的那条加上文件名前缀，一道题都不丢。

    （比如两个文件都没写 id，各自退化成 q-0000；文件内部撞 id 仍由 `load_questions` 报错。）
    """
    seen: set = set()
    for path in paths:
        p = Path(path)
        for q in load_questions(p, aliases):
            if q.qid in seen:
                q.qid = f"{_prefix(p, base)}:{q.qid}"
            if q.qid in seen:
                raise ValueError(f"合并题库时出现重复 id: {q.qid}（来自 {p}）")
            seen.add(q.qid)
            yield p, q


def _prefix(path: Path, base: str | Path | None) -> str:
    """用相对 base 的路径（去后缀）当前缀，保证不同文件的前缀互不相同。"""
    if base:
        try:
            return str(path.resolve().relative_to(Path(base).resolve()).with_suffix(""))
        except ValueError:
            pass  # 不在 base 下面，退回文件名
    return path.stem