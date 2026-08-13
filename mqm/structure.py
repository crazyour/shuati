"""数学结构归一化：把模板变成与具体数字无关的签名。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# 这些字母当作自变量，其余单字母当作系数占位符。题库习惯不同就改这里。
VAR_HINTS = ("x", "y", "z", "t", "u", "v", "θ")

_WS_RE = re.compile(r"\s+")
_SINGLE_LETTER_RE = re.compile(r"^[A-Za-z]$")
_FUNC_CALL_RE = re.compile(r"^[A-Za-z]\([A-Za-z](?:,[A-Za-z])*\)$")

_DEGREE_NAMES = {0: "constant", 1: "linear", 2: "quadratic", 3: "cubic"}

TRIG_FUNCS = ("sin", "cos", "tan", "cot", "sec", "csc")
FUNC_NAMES = TRIG_FUNCS + ("log", "ln", "lg", "exp", "sqrt", "abs")
_FUNC_APPLY_RE = re.compile(r"(" + "|".join(FUNC_NAMES) + r")\(([^()]*)\)")
_FUNC_NAME_RE = re.compile(r"(?:" + "|".join(FUNC_NAMES) + r")(?=\()")
_PURE_POWER_RE = re.compile(r"^[a-zθ]\^(\d+)$")
_PAREN_POWER_RE = re.compile(r"\(([^()]*)\)(?:\^|\*\*)(\d+)")

# 非多项式函数出现时的类型推断
_FUNC_TYPE_NAMES = (
    (TRIG_FUNCS, "trigonometric"),
    (("log", "ln", "lg"), "logarithmic"),
    (("exp",), "exponential"),
    (("sqrt",), "radical"),
)


@dataclass(frozen=True)
class StructureSignature:
    raw_type: Optional[str] = None
    template: Optional[str] = None
    normalized: Optional[str] = None
    monomials: Tuple[str, ...] = ()
    variables: Tuple[str, ...] = ()
    variable_count: Optional[int] = None
    degree: Optional[int] = None
    extras: Dict[str, object] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.raw_type or self.normalized or self.monomials)

    @property
    def functions(self) -> Tuple[str, ...]:
        return tuple(self.extras.get("functions", ()))  # type: ignore[arg-type]

    @property
    def effective_type(self) -> Optional[str]:
        """显式 type 优先，否则从函数种类 / 次数 + 是否含等号推断。"""
        if self.raw_type:
            return self.raw_type
        kind = "equation" if self.extras.get("has_equation") else "function"
        for names, label in _FUNC_TYPE_NAMES:
            if any(f in names for f in self.functions):
                return f"{label}_{kind}"
        if self.degree is None:
            return None
        name = _DEGREE_NAMES.get(self.degree, f"degree{self.degree}")
        return f"{name}_{kind}"


def _split_lhs_rhs(text: str) -> Tuple[Optional[str], str]:
    for op in ("<=", ">=", "=", "<", ">"):
        if op in text:
            lhs, rhs = text.split(op, 1)
            return lhs, rhs
    return None, text


def _canonical_var_set(text: str) -> Tuple[str, ...]:
    """变量识别前先摘掉函数名，否则 sqrt 里的 t、exp 里的 x 会被当成变量。"""
    cleaned = _FUNC_NAME_RE.sub("", text)
    return tuple(v for v in VAR_HINTS if v in cleaned)


CONST_MONOMIAL = "const"


def _var_powers(term: str, variables: Sequence[str]) -> List[str]:
    """一个单项式里出现的 变量^次数，如 "-3x^2*y" -> ["x^2", "y^1"]。"""
    powers: List[str] = []
    for var in variables:
        for match in re.finditer(re.escape(var) + r"(?:\^|\*\*)(\d+)", term):
            powers.append(f"{var}^{match.group(1)}")
        bare = re.sub(re.escape(var) + r"(?:\^|\*\*)\d+", "", term)
        if var in bare:
            powers.append(f"{var}^1")
    return sorted(set(powers))


def _term_atoms(term: str, variables: Sequence[str]) -> List[str]:
    """单项式里的原子：变量幂 x^2，或函数作用 sin(x^1)。常数项返回空列表。

    sin/log/exp 等函数先被摘出来，里面的变量不再计入多项式次数，
    所以 y=a*sin(x)+b 不会被误判成一次函数。
    """
    atoms: List[str] = []
    rest = term
    for match in _FUNC_APPLY_RE.finditer(term):
        inner = _var_powers(match.group(2), variables)
        atoms.append(f"{match.group(1)}({'*'.join(inner) if inner else 'c'})")
        rest = rest.replace(match.group(0), "")
    # (x-h)^2 这类顶点式：括号内变量的次数乘上外层指数
    for match in _PAREN_POWER_RE.finditer(rest):
        exponent = int(match.group(2))
        for power in _var_powers(match.group(1), variables):
            var, inner_exp = power.split("^")
            atoms.append(f"{var}^{int(inner_exp) * exponent}")
        rest = rest.replace(match.group(0), "")
    atoms.extend(_var_powers(rest, variables))
    return sorted(set(atoms))


def _split_terms(side: str) -> List[str]:
    """按顶层 +/- 拆项：括号内部、指数和科学计数法里的符号不拆。"""
    terms: List[str] = []
    buf: List[str] = []
    depth = 0
    for i, ch in enumerate(side):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch in "+-" and depth == 0 and i > 0 and side[i - 1] not in "^*(eE":
            terms.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    terms.append("".join(buf))
    return [t for t in (p.strip().strip("*") for p in terms) if t]


def _monomials(expr: str, variables: Sequence[str]) -> Tuple[str, ...]:
    """表达式包含的单项式集合（去重排序），常数项记作 const。"""
    found: List[str] = []
    for term in _split_terms(expr):
        atoms = _term_atoms(term, variables)
        if atoms:
            found.extend(atoms)
        elif re.search(r"[\da-zA-Z]", term):
            found.append(CONST_MONOMIAL)
    return tuple(sorted(set(found)))


def _term_signature(term: str, variables: Sequence[str]) -> str:
    """单项式签名：系数一律记作 c，只保留变量及其次数。2x^2 和 a*x^2 都是 c*x^2。"""
    atoms = _term_atoms(term, variables)
    return "c*" + "*".join(atoms) if atoms else "c"


def _normalize_side(side: str, variables: Sequence[str]) -> str:
    terms = _split_terms(side)
    return "+".join(sorted(_term_signature(t, variables) for t in terms)) or "c"


def _is_dependent_variable(lhs: str) -> bool:
    """y = … / S = … / f(x) = … 左边只是因变量，不携带结构信息。"""
    return bool(_SINGLE_LETTER_RE.match(lhs) or _FUNC_CALL_RE.match(lhs))


def _normalize_expression(text: str) -> str:
    """把模板变成与数字、系数字母无关的规范串。"""
    lhs, rhs = _split_lhs_rhs(text)
    variables = _canonical_var_set(text)
    right = _normalize_side(rhs, variables)
    if lhs is None:
        return right
    left = "y" if _is_dependent_variable(lhs) else _normalize_side(lhs, variables)
    return f"{left}={right}"


def parse_structure(value: object) -> StructureSignature:
    """接受 dict 或裸字符串模板。"""
    if value is None:
        return StructureSignature()

    if isinstance(value, str):
        data: Dict[str, object] = {"template": value}
    elif isinstance(value, dict):
        data = dict(value)
    else:
        raise TypeError(f"math_structure 必须是 str 或 dict，得到 {type(value)!r}")

    raw_type = data.get("type")
    template = data.get("template") or data.get("expr") or data.get("formula")
    declared_count = data.get("variable_count")
    extras = {
        k: v
        for k, v in data.items()
        if k not in {"type", "template", "expr", "formula", "variable_count"}
    }

    if not template:
        return StructureSignature(
            raw_type=str(raw_type) if raw_type else None,
            variable_count=int(declared_count) if declared_count is not None else None,
            extras=extras,
        )

    compact = _WS_RE.sub("", str(template)).lower().replace("**", "^")
    lhs, rhs = _split_lhs_rhs(compact)
    # 变量识别前先摘掉函数名，否则 sqrt 里的 t、exp 里的 x 会被当成变量
    variables = _canonical_var_set(_FUNC_NAME_RE.sub("", compact))

    # 结构信息在变量更密集的那一侧：y=ax^2+... 取右式，ax^2+...=0 取左式。
    def var_load(side: str) -> int:
        return sum(side.count(v) for v in variables)

    expr = rhs if lhs is None or var_load(rhs) >= var_load(lhs) else lhs
    expr_variables = tuple(v for v in variables if v in expr) or variables
    monos = _monomials(expr, expr_variables)
    degrees = [int(m.group(1)) for m in map(_PURE_POWER_RE.match, monos) if m]
    # 左边不是单纯的因变量（y= / f(x)= / S=）才算方程
    extras["has_equation"] = lhs is not None and not _is_dependent_variable(lhs)
    extras["functions"] = tuple(sorted({m.group(1) for m in _FUNC_APPLY_RE.finditer(compact)}))

    return StructureSignature(
        raw_type=str(raw_type) if raw_type else None,
        template=str(template),
        normalized=_normalize_expression(compact),
        monomials=monos,
        variables=variables,
        variable_count=int(declared_count) if declared_count is not None else len(expr_variables),
        degree=max(degrees) if degrees else None,
        extras=extras,
    )
