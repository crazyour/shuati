"""按科目 / 学校 / 专攻 三级组织的题库：

    data/<科目>/<学校>/<专攻>.json

检索范围（scope）有三级，写成一个字符串：

    "__all__"                  全部题目
    "线性代数"                  某个科目
    "线性代数/九州大学"          科目下的某所学校
    "线性代数/九州大学/情报理工"  科目下某所学校的某个专攻

来源取每道题的 `school` / `学校` / `source` / `来源` 字段，没写退回文件名。
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


# ---------- 三级结构：科目 / 学校 / 专攻 ----------

# 解析结果
StructuredPath = Tuple[str, str, str]  # (subject, school, senkou)


def structured_files(subject: str, root: str | Path | None = None) -> List[Tuple[StructuredPath, Path]]:
    """某科目下严格按 `科目/学校/专攻.json` 布局的题库文件。

    只接受「科目/学校/专攻.json」3 段路径；其它散乱结构（旧格式）被忽略。
    """
    r = _root(root)
    d = r if subject == ALL_SUBJECTS else r / subject
    if not d.is_dir():
        return []
    out: List[Tuple[StructuredPath, Path]] = []
    for path in d.rglob("*.json"):
        if path.is_file() and path.suffix.lower() in QUESTION_SUFFIXES:
            rel_parts = path.relative_to(d).parts
            # __all__ 时是「科目/学校/专攻.json」(3 段)；否则「学校/专攻.json」(2 段)
            if subject == ALL_SUBJECTS:
                if len(rel_parts) != 3:
                    continue
                subj, school, fname = rel_parts
            else:
                if len(rel_parts) != 2:
                    continue
                subj = subject
                school, fname = rel_parts
            if not fname.endswith(".json"):
                continue
            senkou = fname[:-len(".json")]
            out.append(((subj, school, senkou), path))
    out.sort()
    return out


def list_schools(subject: str, root: str | Path | None = None) -> List[str]:
    """某科目下有哪些学校。"""
    seen: set = set()
    for (s, school, _), _ in structured_files(subject, root):
        seen.add(school)
    return sorted(seen)


def list_senkou(subject: str, school: str, root: str | Path | None = None) -> List[str]:
    """某科目 + 学校下有哪些专攻。"""
    seen: set = set()
    for (s, sc, senkou), _ in structured_files(subject, root):
        if sc == school:
            seen.add(senkou)
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


def split_scope(scope: str) -> Tuple[str, str, str]:
    """"线性代数/九州大学/情报理工" -> 三元组；不足三段后面为空。"""
    parts = (scope or "").split("/")
    while len(parts) < 3:
        parts.append("")
    return tuple(parts)  # type: ignore[return-value]


def load_scope(scope: str, aliases: Aliases = None, root: str | Path | None = None) -> List[Question]:
    """按检索范围加载题目。范围写错会报错，并把可选项列出来。"""
    r = _root(root)
    subject, school, senkou = split_scope(scope)
    if school:
        # 新结构：subject/school[/senkou]
        files = [p for ((s, sc, sk), p) in structured_files(subject, r)
                 if sc == school and (not senkou or sk == senkou)]
        if not files:
            raise ValueError(f"{scope!r} 下没有题库文件")
        return load_question_files(files, aliases, base=r)
    # 旧兼容：仅按 subject
    files = subject_files(subject, r)
    if not files:
        available = "、".join([ALL_SUBJECTS, *list_subjects(r)])
        raise ValueError(f"科目 {subject!r} 下没有题库文件；可选：{available}")
    if not senkou:
        return load_question_files(files, aliases, base=r)
    groups = group_by_source(files, aliases, r)
    if senkou not in groups:
        raise ValueError(f"科目 {subject!r} 下没有来源 {senkou!r}；可选：{'、'.join(groups)}")
    return groups[senkou]


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
