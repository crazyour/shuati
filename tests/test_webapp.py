import io
import json

import pytest

from webapp.server import create_app, question_text
from mqm import ALL_SUBJECTS, question_from_dict
from pipeline.ocr import available_backends

VALID_QUERY = {
    "knowledge_points": ["二次函数", "最值"],
    "question_type": "求最小值",
    "method": ["配方法", "顶点"],
    "math_structure": "y=ax^2+bx+c",
    "difficulty": 2,
}


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_home_page_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "相似度匹配" not in body                         # 独立匹配页已移除
    assert 'id="browse-subject"' in body                   # 题目库左侧的科目下拉
    assert 'id="browse-school"' in body                    # 题目库左侧的学校下拉
    assert 'id="browse-senkou"' in body                    # 题目库左侧的专攻下拉
    assert 'id="similar-drawer"' in body                   # 相似题结果使用共享抽屉


def test_match_returns_question_metadata(client):
    res = client.post("/api/match", json={"query": VALID_QUERY, "topk": 3, "min_score": 0})
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["matches"]) == 3
    assert all({"id", "school", "year", "text", "score"} <= set(m) for m in body["matches"])
    assert "最小值" in body["matches"][0]["text"]


def test_match_accepts_json_string(client):
    import json

    res = client.post("/api/match", json={"query": json.dumps(VALID_QUERY), "min_score": 0})
    assert res.status_code == 200
    assert res.get_json()["matches"]


def test_similar_accepts_question_id(subject_app):
    browse = subject_app.get("/api/browse/questions?subject=线性代数").get_json()
    question_id = browse["questions"][0]["id"]
    res = subject_app.post(
        "/api/similar", json={"id": question_id, "subject": "线性代数", "min_score": 0}
    )
    assert res.status_code == 200
    assert res.is_json
    assert all({"id", "score", "text"} <= set(item) for item in res.get_json()["matches"])


def test_topk_is_clamped(client):
    res = client.post("/api/match", json={"query": VALID_QUERY, "topk": 999})
    assert res.status_code == 200
    assert len(res.get_json()["matches"]) <= 50


def test_bad_json_reports_error(client):
    res = client.post("/api/match", json={"query": "{不是JSON}"})
    assert res.status_code == 400
    assert "JSON 格式有误" in res.get_json()["error"]


def test_empty_question_reports_error(client):
    res = client.post("/api/match", json={"query": {}})
    assert res.status_code == 400
    assert "字段" in res.get_json()["error"]


# ---------- 选检索范围（科目 / 学校）----------

KYUSHU_1 = {
    "id": "la-k1",
    "school": "九州大学",
    "text": "求矩阵 $A$ 的特征值与特征向量。",
    "knowledge_points": ["特征值与特征向量", "实对称矩阵"],
    "question_type": "求特征值",
    "method": ["特征多项式"],
}
KYUSHU_2 = {
    "id": "la-k2",
    "school": "九州大学",
    "text": "设 $A$ 可对角化，求 $A^n$。",
    "knowledge_points": ["矩阵幂", "特征分解"],
    "question_type": "求矩阵幂",
    "method": ["对角化"],
}
TOKYO_1 = {
    "id": "la-t1",
    "school": "东京大学",
    "text": r"证明 $\operatorname{rank}(AB)\le\operatorname{rank}(A)$。",
    "knowledge_points": ["矩阵秩"],
    "question_type": "证明不等式",
    "method": ["秩不等式"],
}
CALCULUS_Q = {   # 没写 school，来源退化成文件名「题库」
    "id": "ca-1",
    "text": r"求 $\int x e^x\,dx$。",
    "knowledge_points": ["不定积分", "分部积分"],
    "question_type": "求积分",
    "method": ["分部积分法"],
}


@pytest.fixture(scope="module")
def subject_app(tmp_path_factory):
    """临时科目目录（新三级结构）：

    data/
      线性代数/九州大学/
        情报理工.json   （KYUSHU_1, KYUSHU_2）
        东京大学_情报理工.json   （TOKYO_1）
      微积分/九州大学/
        情报理工.json   （CALCULUS_Q）
      空科目/                       （无题库文件，应不出现）
    """
    root = tmp_path_factory.mktemp("subjects")
    # 线性代数
    _write_subject(root, "线性代数", "九州大学", "情报理工.json",
                   [KYUSHU_1, KYUSHU_2])
    _write_subject(root, "线性代数", "东京大学", "情报理工.json",
                   [TOKYO_1])
    # 微积分
    _write_subject(root, "微积分", "九州大学", "情报理工.json",
                   [CALCULUS_Q])
    # 空目录（无题库文件）
    (root / "空科目").mkdir()
    app = create_app(data_root=root)
    app.config.update(TESTING=True)
    return app.test_client()


def _scope_tree(client):
    """页面上的按钮组数据（和 /api/subjects 的 tree 是同一份）。"""
    html = client.get("/").get_data(as_text=True)
    raw = html.split('id="scope-tree" type="application/json">')[1].split("</script>")[0]
    return json.loads(raw)


def test_home_page_renders_the_scope_chips(subject_app):
    html = subject_app.get("/").get_data(as_text=True)
    assert 'id="similar-drawer"' in html
    assert "空科目" not in html            # 没有 JSON 的目录不算科目

    tree = _scope_tree(subject_app)
    # 顶层：全部题目 + 各科目 + 默认题库
    assert [(n["label"], n["count"]) for n in tree] == [
        ("全部题目", 4), ("微积分", 1), ("线性代数", 3),
        ("默认题库（questions.sample.json）", 12),
    ]
    # 线性代数：科目 → 学校 → 专攻（3 层）
    linalg = next(n for n in tree if n["label"] == "线性代数")
    assert [c["label"] for c in linalg["children"]] == ["全部", "九州大学", "东京大学"]
    school = next(c for c in linalg["children"] if c["label"] == "九州大学")
    assert [(c["label"], c["count"]) for c in school["children"]] == [("情报理工", 2)]
    # 微积分：每个科目节点下含「全部」+ 学校节点
    calculus = next(n for n in tree if n["label"] == "微积分")
    assert [c["label"] for c in calculus["children"]] == ["全部", "九州大学"]


def test_subjects_api(subject_app):
    body = subject_app.get("/api/subjects").get_json()
    # 所有 scope key（按字母序，3 级）
    values = [s["value"] for s in body["subjects"]]
    assert values == [
        ALL_SUBJECTS,
        "微积分", "微积分/九州大学", "微积分/九州大学/情报理工",
        "线性代数", "线性代数/东京大学", "线性代数/东京大学/情报理工",
        "线性代数/九州大学", "线性代数/九州大学/情报理工",
        "",
    ]
    assert [n["value"] for n in body["tree"]] == [ALL_SUBJECTS, "微积分", "线性代数", ""]
    assert body["default"] == ALL_SUBJECTS
    assert body["min_score"] > 0           # 默认带阈值


def test_scope_limits_the_search(subject_app):
    """选了微积分，就算 query 是线代题，也只可能从微积分里出结果。"""
    res = subject_app.post(
        "/api/match", json={"query": KYUSHU_1, "subject": "微积分", "min_score": 0}
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["db_size"] == 1
    assert body["subject_label"] == "微积分 · 全部"
    assert body["matches"][0]["text"] == CALCULUS_Q["text"]


def test_source_scope_narrows_to_one_school(subject_app):
    query = {k: v for k, v in KYUSHU_1.items() if k != "id"}
    res = subject_app.post(
        "/api/match", json={"query": query, "subject": "线性代数/九州大学/情报理工"}
    )
    body = res.get_json()
    assert body["db_size"] == 2                      # 只有九州大学那两题
    assert body["matches"][0]["text"] == KYUSHU_1["text"]
    assert TOKYO_1["text"] not in [m["text"] for m in body["matches"]]


def test_all_subjects_searches_every_folder(subject_app):
    query = {k: v for k, v in CALCULUS_Q.items() if k != "id"}   # 带 id 会被当成自己而跳过
    res = subject_app.post("/api/match", json={"query": query, "subject": ALL_SUBJECTS})
    body = res.get_json()
    assert body["db_size"] == 4
    assert body["matches"][0]["text"] == CALCULUS_Q["text"]      # 全部题目里也是微积分那题最像


def test_unknown_subject_reports_choices(subject_app):
    res = subject_app.post("/api/match", json={"query": KYUSHU_1, "subject": "线代"})
    assert res.status_code == 400
    error = res.get_json()["error"]
    assert "没有这个科目：线代" in error and "线性代数" in error


# ---------- 题库热加载 ----------

def _write_subject(root, subject, school, filename, questions):
    """新三级结构：data/<科目>/<学校>/<filename>（filename 即专攻）"""
    (root / subject / school).mkdir(parents=True, exist_ok=True)
    (root / subject / school / filename).write_text(
        json.dumps(questions, ensure_ascii=False), encoding="utf-8"
    )


def _scope_counts(client):
    return {s["value"]: s["count"] for s in client.get("/api/subjects").get_json()["subjects"]}


@pytest.fixture
def live_client(tmp_path):
    """每个用例一份可改的题库目录。"""
    _write_subject(tmp_path, "线性代数", "九州大学", "情报理工.json",
                   [{"id": "a1", "school": "九州大学", "text": "题 A", "knowledge_points": ["矩阵"]}])
    app = create_app(data_root=tmp_path)
    app.config.update(TESTING=True)
    return app.test_client(), tmp_path


def test_new_file_shows_up_without_restart(live_client):
    client, root = live_client
    assert _scope_counts(client)["线性代数"] == 1

    _write_subject(root, "线性代数", "东北大学", "情报理工.json", [
        {"id": "b1", "school": "东北大学", "text": "题 B", "knowledge_points": ["秩"]},
        {"id": "b2", "school": "东北大学", "text": "题 C", "knowledge_points": ["核"]},
    ])
    counts = _scope_counts(client)
    assert counts["线性代数"] == 3 and counts["线性代数/东北大学/情报理工"] == 2   # 新学校自己成一档

    linalg = next(n for n in _scope_tree(client) if n["value"] == "线性代数")
    # 找到东北大学 → 情报理工 子节点
    school = next(c for c in linalg["children"] if c["value"] == "线性代数/东北大学")
    assert ("情报理工", 2) in [(c["label"], c["count"]) for c in school["children"]]


def test_new_subject_folder_shows_up_without_restart(live_client):
    client, root = live_client
    _write_subject(root, "微积分", "九州大学", "情报理工.json",
                   [{"id": "c1", "text": "题 D", "knowledge_points": ["积分"]}])
    assert _scope_counts(client)["微积分"] == 1


def test_edited_question_is_reindexed(live_client):
    client, root = live_client
    _write_subject(root, "线性代数", "九州大学", "情报理工.json", [
        {"id": "a1", "school": "九州大学", "text": "题 A 改过了", "knowledge_points": ["矩阵"]},
        {"id": "a2", "school": "九州大学", "text": "题 F", "knowledge_points": ["矩阵"]},
    ])
    body = client.post(
        "/api/match", json={"query": {"knowledge_points": ["矩阵"]}, "subject": "线性代数", "min_score": 0}
    ).get_json()
    assert body["db_size"] == 2
    assert "题 A 改过了" in [m["text"] for m in body["matches"]]


def test_deleted_file_disappears(live_client):
    client, root = live_client
    _write_subject(root, "线性代数", "东北大学", "情报理工.json",
                   [{"id": "b1", "school": "东北大学", "text": "题 B", "knowledge_points": ["秩"]}])
    assert "线性代数/东北大学/情报理工" in _scope_counts(client)

    (root / "线性代数" / "东北大学" / "情报理工.json").unlink()
    assert "线性代数/东北大学/情报理工" not in _scope_counts(client)


def test_watch_can_be_disabled(tmp_path):
    _write_subject(tmp_path, "线性代数", "九州大学", "情报理工.json",
                   [{"id": "a1", "school": "九州大学", "text": "题 A", "knowledge_points": ["矩阵"]}])
    app = create_app(data_root=tmp_path, watch=False)
    app.config.update(TESTING=True)
    client = app.test_client()

    _write_subject(tmp_path, "微积分", "九州大学", "情报理工.json",
                   [{"id": "c1", "text": "题 D", "knowledge_points": ["积分"]}])
    assert "微积分" not in _scope_counts(client)          # 关掉就一直用启动时那份


# ---------- 检索阈值 ----------

def test_threshold_hides_cross_subject_matches(subject_app):
    """线代题在微积分里搜：分数够不到阈值，一条都不给，而不是拿积分题凑数。"""
    res = subject_app.post("/api/match", json={"query": KYUSHU_1, "subject": "微积分"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["matches"] == []
    assert body["best_score"] < body["min_score"]   # 会告诉你最相似的一条差多少
    assert body["filtered"] == 1


def test_threshold_can_be_relaxed_per_request(subject_app):
    res = subject_app.post(
        "/api/match", json={"query": KYUSHU_1, "subject": "微积分", "min_score": 0.01}
    )
    body = res.get_json()
    assert body["min_score"] == 0.01
    assert body["matches"] and body["filtered"] == 0


def test_threshold_is_clamped_to_0_1(subject_app):
    for sent, expected in ((5, 1.0), (-2, 0.0), ("不是数字", 0.35)):
        body = subject_app.post(
            "/api/match", json={"query": KYUSHU_1, "subject": "线性代数", "min_score": sent}
        ).get_json()
        assert body["min_score"] == expected


def test_same_subject_still_passes_the_threshold(subject_app):
    query = {k: v for k, v in KYUSHU_2.items() if k != "id"}
    body = subject_app.post("/api/match", json={"query": query, "subject": "线性代数"}).get_json()
    assert body["matches"][0]["text"] == KYUSHU_2["text"]
    assert body["best_score"] >= body["min_score"]


def test_image_endpoint_validates_subject(subject_app):
    res = subject_app.post(
        "/api/match-image",
        data={"image": (io.BytesIO(b"x"), "q.png"), "subject": "不存在"},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert "没有这个科目" in res.get_json()["error"]


def test_missing_subject_falls_back_to_default_db(client):
    """老调用方不传 subject 时，仍然用 --db 那个题库。"""
    res = client.post("/api/match", json={"query": VALID_QUERY})
    body = res.get_json()
    assert res.status_code == 200
    assert body["subject"] == "" and "questions.sample.json" in body["subject_label"]


def test_question_text_falls_back_when_no_stem():
    q = question_from_dict({"id": "q-x", "knowledge_points": ["二次函数"], "question_type": "求最值"})
    text = question_text(q)
    assert "未提供题目原文" in text and "二次函数" in text


def test_question_text_reads_alternative_keys():
    q = question_from_dict({"id": "q-y", "stem": "求 y = x^2 的最小值。"})
    assert question_text(q) == "求 y = x^2 的最小值。"


# ---------- 图片入口 ----------

def _question_image_bytes():
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (880, 120), "white")
    ImageDraw.Draw(img).text(
        (24, 34),
        "已知二次函数 y = 3x² + 6x - 2，求它的最小值。",
        font=ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 32),
        fill="black",
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_image_upload_rejects_bad_suffix(client):
    res = client.post(
        "/api/match-image",
        data={"image": (io.BytesIO(b"not an image"), "题目.txt")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert "不支持的图片格式" in res.get_json()["error"]


def test_image_upload_requires_a_file(client):
    res = client.post("/api/match-image", data={}, content_type="multipart/form-data")
    assert res.status_code == 400


def test_missing_api_key_returns_503(client, monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setattr("pipeline.llm.load_env_file", lambda *a, **k: None)
    res = client.post(
        "/api/match-image",
        data={"image": (io.BytesIO(_question_image_bytes()), "q.png")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 503
    assert "MINIMAX_API_KEY" in res.get_json()["error"]


@pytest.mark.skipif("vision" not in available_backends(), reason="需要 macOS Vision (pip install ocrmac)")
def test_image_pipeline_returns_only_question_texts(client, monkeypatch):
    """图片 -> OCR -> (假)模型 -> 匹配；结果列表仍然只有题目。"""
    model_json = {
        "knowledge_points": ["二次函数", "函数最值", "顶点"],
        "question_type": "求最小值",
        "method": ["配方法", "顶点式"],
        "math_structure": {"type": "quadratic_function", "template": "y = a*x^2 + b*x + c", "variable_count": 1},
        "difficulty": 2,
    }

    def transport(url, headers, payload, timeout):
        return 200, {"content": [
            {"type": "thinking", "thinking": "…"},
            {"type": "text", "text": json.dumps(model_json, ensure_ascii=False)},
        ]}

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr("pipeline.llm._requests_transport", transport)

    res = client.post(
        "/api/match-image",
        data={"image": (io.BytesIO(_question_image_bytes()), "q.png"), "topk": "3"},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["matches"]) == 3
    assert all({"id", "school", "year", "text", "score"} <= set(m) for m in body["matches"])
    assert "二次函数" in body["ocr_text"]                          # 过程数据单独放
    assert body["question_json"]["question_type"] == "求最小值"
    assert body["ocr_backend"] == "vision"
