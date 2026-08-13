from pathlib import Path

import pytest

from mqm import (
    QuestionIndex,
    aliases_from_config,
    get_encoder,
    load_config,
    load_question,
    load_questions,
    parse_structure,
    question_from_dict,
    score_pair,
    set_similarity,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def config():
    return load_config(ROOT / "config" / "default.json")


@pytest.fixture(scope="module")
def aliases(config):
    return aliases_from_config(config)


@pytest.fixture(scope="module")
def encoder():
    return get_encoder("hashing")


@pytest.fixture(scope="module")
def index(config, aliases):
    return QuestionIndex(load_questions(ROOT / "data" / "questions.sample.json", aliases), config=config)


# ---------- 结构归一化 ----------

def test_structure_ignores_numbers():
    a = parse_structure({"type": "quadratic_function", "template": "y = 2x^2 - 3x + 1"})
    b = parse_structure({"type": "quadratic_function", "template": "y = a*x^2 + b*x + c"})
    assert a.normalized == b.normalized == "y=c+c*x^1+c*x^2"
    assert a.monomials == b.monomials == ("const", "x^1", "x^2")
    assert a.degree == 2


def test_structure_vertex_form_is_quadratic():
    """顶点式 y=a(x-h)^2+k 的次数不能被括号骗成 1。"""
    s = parse_structure("y = a*(x-h)^2 + k")
    assert s.degree == 2
    assert s.effective_type == "quadratic_function"


def test_structure_non_polynomial_functions():
    """sqrt 里的 t、exp 里的 x 不能被当成变量；三角/对数要能推断类型。"""
    trig = parse_structure("y = a*sin(2x) + b")
    assert trig.degree is None
    assert trig.effective_type == "trigonometric_function"
    assert parse_structure("y = log(x) + 2").effective_type == "logarithmic_function"
    assert parse_structure("y = sqrt(x + 1)").variables == ("x", "y")


def test_structure_accepts_bare_string_and_infers_type():
    s = parse_structure("y=ax^2+bx+c")
    assert s.degree == 2
    assert s.variable_count == 1
    assert s.effective_type == "quadratic_function"


def test_structure_equation_vs_function_differ():
    eq = parse_structure("a*x^2 + b*x + c = 0")
    fn = parse_structure("y = a*x^2 + b*x + c")
    assert eq.effective_type == "quadratic_equation"
    assert fn.effective_type == "quadratic_function"
    assert eq.monomials == fn.monomials  # 结构同，语义不同 -> 靠 type 区分


def test_structure_variable_count_counts_independent_vars():
    """variable_count 只数表达式侧的自变量，因变量 z 不计入。"""
    s = parse_structure("z = x^2 + y^2 + a*x + b*y")
    assert s.variable_count == 2
    assert parse_structure("y = x^2 - 4x + 7").variable_count == 1


# ---------- 集合相似度 ----------

def test_set_similarity_modes(encoder):
    q = ["二次函数", "函数最值"]
    c = ["二次函数", "函数最值", "顶点"]
    f1 = set_similarity(encoder, q, c, mode="f1")
    cov = set_similarity(encoder, q, c, mode="query_coverage")
    assert cov == pytest.approx(1.0, abs=1e-6)  # query 的考点全被覆盖
    assert f1 < cov  # candidate 多出的考点会被 f1 惩罚
    assert set_similarity(encoder, q, c, mode="jaccard") == pytest.approx(2 / 3)


def test_set_similarity_missing_side_returns_none(encoder):
    assert set_similarity(encoder, [], ["二次函数"], mode="f1") is None


def test_solution_steps_lcs_is_order_sensitive(encoder):
    steps = ["识别二次函数", "完成平方", "读取最小值"]
    same = set_similarity(encoder, steps, steps, mode="lcs")
    reversed_ = set_similarity(encoder, steps, list(reversed(steps)), mode="lcs")
    assert same == pytest.approx(1.0, abs=1e-6)
    assert reversed_ < same


# ---------- 打分 ----------

def test_readme_example_score(encoder, config, aliases):
    query = question_from_dict({
        "id": "query",
        "knowledge_points": ["二次函数", "最值"],
        "question_type": "求最小值",
        "method": ["配方法", "顶点"],
        "math_structure": "y=ax^2+bx+c",
        "difficulty": 2,
    }, aliases)
    candidate = question_from_dict({
        "id": "cand",
        "knowledge_points": ["二次函数", "最值", "顶点"],
        "question_type": "求最小值",
        "method": ["配方法", "顶点"],
        "math_structure": "y=ax^2+bx+c",
        "difficulty": 3,
    }, aliases)
    result = score_pair(query, candidate, encoder, config)
    # 对应用户给的算例：K≈0.94 M=1.00 S=1.00 Q=1.00 D=0.80 -> 0.966
    assert result.total == pytest.approx(0.966, abs=0.01)
    assert result.breakdown["question_type"] == pytest.approx(1.0)
    assert result.breakdown["math_structure"] == pytest.approx(1.0)
    assert result.breakdown["difficulty"] == pytest.approx(0.8)
    assert result.breakdown["knowledge_points"] > 0.9  # candidate 多一个考点，只轻罚


def test_missing_field_is_skipped_and_weights_renormalize(encoder, config, aliases):
    base = {
        "knowledge_points": ["二次函数", "函数最值"],
        "question_type": "求最值",
        "method": ["配方法"],
        "math_structure": "y=ax^2+bx+c",
    }
    query = question_from_dict({"id": "q", **base}, aliases)          # 没有 difficulty
    candidate = question_from_dict({"id": "c", **base, "difficulty": 4}, aliases)
    result = score_pair(query, candidate, encoder, config)
    assert "difficulty" in result.skipped
    assert result.total == pytest.approx(1.0, abs=1e-6)  # 缺字段不该拉低总分
    assert result.weight_covered == pytest.approx(0.95, abs=1e-6)


def test_same_concept_beats_surface_similar(index, aliases):
    """题A(考点考法一致、只有数字不同) 必须排在 题B(文字公式很像但问法不同) 之前。"""
    query = load_question(ROOT / "examples" / "query.json", aliases)
    ranked = [m.qid for m in index.match(query, topk=len(index))]
    assert ranked[0] == "q-0001"
    assert ranked.index("q-0001") < ranked.index("q-0002")
    assert ranked.index("q-0001") < ranked.index("q-0003")


def test_knn_baseline_ranks_surface_similar_higher(index, aliases):
    """对照组：整份 JSON 直接 KNN 会把"文字公式几乎一样但问对称轴"的 q-0002 抬得更高。"""
    query = load_question(ROOT / "examples" / "query.json", aliases)
    knn_rank = [qid for qid, _ in index.knn(query, topk=len(index))].index("q-0002")
    field_rank = [
        m.qid for m in index.match(query, topk=len(index), rescore_all=True)
    ].index("q-0002")
    assert knn_rank < field_rank


def test_method_difference_is_penalised(index, aliases):
    """同样是求最小值，但用导数法的题应该低于用配方法的题。"""
    query = load_question(ROOT / "examples" / "query.json", aliases)
    scores = {m.qid: m.score for m in index.match(query, topk=len(index), rescore_all=True)}
    assert scores["q-0001"] > scores["q-0006"]
    assert scores["q-0005"] > scores["q-0007"]


def test_recall_pool_contains_expected_candidates(index, aliases):
    query = load_question(ROOT / "examples" / "query.json", aliases)
    pool = index.recall(query)
    assert "q-0001" in pool
    assert query.qid not in [m.qid for m in index.match(query, topk=3)]


def test_weight_override_changes_ranking(config, aliases):
    """把权重全压到 question_type 上，问法不同的题应该掉下去。
    注意 config 里的 weights 是"按字段覆盖"，没写的字段沿用默认权重，所以这里要显式置 0。"""
    cfg = {
        **config,
        "weights": {
            "question_type": 1.0,
            "knowledge_points": 0.0,
            "method": 0.0,
            "math_structure": 0.0,
            "difficulty": 0.0,
            "solution_steps": 0.0,
        },
    }
    idx = QuestionIndex(load_questions(ROOT / "data" / "questions.sample.json", aliases), config=cfg)
    query = load_question(ROOT / "examples" / "query.json", aliases)
    scores = {m.qid: m.score for m in idx.match(query, topk=len(idx), rescore_all=True)}
    assert scores["q-0001"] == pytest.approx(1.0)  # 求最小值 -> 求最值，别名归一后完全一致
    assert scores["q-0002"] < 0.9


def test_duplicate_ids_rejected(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text('[{"id": "a"}, {"id": "a"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="重复 id"):
        load_questions(p)


def test_cli_match_runs(capsys):
    from mqm.cli import main

    rc = main([
        "match",
        "--query", str(ROOT / "examples" / "query.json"),
        "--db", str(ROOT / "data" / "questions.sample.json"),
        "--topk", "3",
        "--explain",
        "--baseline",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "q-0001" in out and "baseline" in out
