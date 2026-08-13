import io
import json

import pytest

from webapp.server import create_app, question_text
from mqm import question_from_dict
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
    assert "相似题匹配" in res.get_data(as_text=True)


def test_match_returns_only_question_text(client):
    res = client.post("/api/match", json={"query": VALID_QUERY, "topk": 3})
    assert res.status_code == 200
    body = res.get_json()
    assert len(body["matches"]) == 3
    # 结果只显示题目：每条只有 text，不带分数/字段明细
    assert all(set(m) == {"text"} for m in body["matches"])
    assert "最小值" in body["matches"][0]["text"]


def test_match_accepts_json_string(client):
    import json

    res = client.post("/api/match", json={"query": json.dumps(VALID_QUERY)})
    assert res.status_code == 200
    assert res.get_json()["matches"]


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
    assert all(set(m) == {"text"} for m in body["matches"])       # 结果只显示题目
    assert "二次函数" in body["ocr_text"]                          # 过程数据单独放
    assert body["question_json"]["question_type"] == "求最小值"
    assert body["ocr_backend"] == "vision"
