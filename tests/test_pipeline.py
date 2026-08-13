import json
from pathlib import Path

import pytest

from mqm import load_config
from pipeline import extract_from_text, normalize_question_json
from pipeline.llm import (
    LLMConfig,
    LLMHTTPError,
    LLMOutputError,
    MissingAPIKeyError,
    complete,
    extract_json_object,
)
from pipeline.ocr import available_backends, clean_question_text, ocr_image

MODEL_JSON = {
    "knowledge_points": ["二次函数", "函数最值", "顶点"],
    "question_type": "求最小值",
    "method": ["配方法", "顶点式"],
    "solution_steps": ["识别二次函数", "配成完全平方", "读取最小值"],
    "math_structure": {"type": "quadratic_function", "template": "y = a*x^2 + b*x + c", "variable_count": 1},
    "difficulty": 2,
}


def fake_transport(payload_out=None, status=200, body=None):
    """假的 HTTP 层：记录请求、返回预设响应，测试不联网。"""
    captured = {} if payload_out is None else payload_out

    def transport(url, headers, payload, timeout):
        captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return status, body if body is not None else _anthropic_body(json.dumps(MODEL_JSON, ensure_ascii=False))

    return transport, captured


def _anthropic_body(text, with_thinking=True):
    content = []
    if with_thinking:
        content.append({"type": "thinking", "thinking": "先判断是不是二次函数…"})
    content.append({"type": "text", "text": text})
    return {"content": content, "stop_reason": "end_turn"}


@pytest.fixture
def config():
    cfg = load_config()
    cfg["llm"]["api_key"] = "test-key"
    return cfg


# ---------- JSON 抠取 ----------

def test_extract_json_plain():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_from_code_fence():
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_surrounding_prose():
    text = '好的，我分析后得到：\n{"a": {"b": 2}}\n希望有帮助。'
    assert extract_json_object(text) == {"a": {"b": 2}}


def test_extract_json_handles_braces_inside_strings():
    assert extract_json_object('{"t": "y = {x}", "n": 1}') == {"t": "y = {x}", "n": 1}


def test_extract_json_reports_missing_and_broken():
    with pytest.raises(LLMOutputError, match="没有输出 JSON"):
        extract_json_object("我不知道这道题。")
    with pytest.raises(LLMOutputError, match="括号没闭合"):
        extract_json_object('{"a": 1')


# ---------- 模型输出归一化 ----------

def test_normalize_coerces_types():
    data = normalize_question_json({
        "knowledge_points": "二次函数",           # 单个字符串 -> 列表
        "question_type": ["求最小值", "求最值"],   # 列表 -> 取第一个
        "method": ["配方法", "配方法", " "],       # 去重去空
        "math_structure": {"type": "quadratic_function", "variable_count": "1"},
        "difficulty": "4.6",                      # 字符串小数 -> 取整
    }, ocr_text="3. 已知 y=x2，求最小值。")
    assert data["knowledge_points"] == ["二次函数"]
    assert data["question_type"] == "求最小值"
    assert data["method"] == ["配方法"]
    assert data["math_structure"]["variable_count"] == 1
    assert data["difficulty"] == 5
    assert data["text"] == "已知 y=x2，求最小值。"  # 行首题号被去掉


def test_normalize_clamps_difficulty_and_drops_junk():
    data = normalize_question_json({"difficulty": -3, "unknown_field": "x", "method": 123})
    assert data["difficulty"] == 1
    assert "unknown_field" not in data
    assert "method" not in data


def test_normalize_accepts_string_math_structure():
    assert normalize_question_json({"math_structure": "y=ax^2+bx+c"})["math_structure"] == "y=ax^2+bx+c"


# ---------- LLM 客户端 ----------

def test_anthropic_request_shape(config):
    transport, captured = fake_transport()
    cfg = LLMConfig.from_config(config)
    cfg.api_key = "test-key"
    complete("系统提示", "用户输入", cfg, transport)

    assert captured["url"].endswith("/messages")
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["payload"]["model"] == "MiniMax-M2.7"
    assert captured["payload"]["system"] == "系统提示"
    # M2.7 强制思考，带 temperature 容易被拒，默认就不发
    assert "temperature" not in captured["payload"]


def test_openai_style_request_shape():
    transport, captured = fake_transport(
        body={"choices": [{"message": {"content": '{"difficulty": 3}'}}]}
    )
    cfg = LLMConfig(api_style="openai", api_key="k")
    assert complete("sys", "user", cfg, transport) == '{"difficulty": 3}'
    assert captured["url"].endswith("/chat/completions")
    assert captured["payload"]["messages"][0]["role"] == "system"


def test_thinking_blocks_are_skipped():
    transport, _ = fake_transport(body=_anthropic_body('{"ok": 1}', with_thinking=True))
    assert complete("s", "u", LLMConfig(api_key="k"), transport) == '{"ok": 1}'


def test_http_errors_carry_hints():
    for status, needle in ((401, "MINIMAX_API_KEY"), (404, "base_url")):
        transport, _ = fake_transport(status=status, body={"error": "nope"})
        with pytest.raises(LLMHTTPError, match=needle):
            complete("s", "u", LLMConfig(api_key="k"), transport)


def test_missing_api_key_is_explained(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.setattr("pipeline.llm.ENV_FILE", Path("/nonexistent/.env"))
    with pytest.raises(MissingAPIKeyError, match="MINIMAX_API_KEY"):
        LLMConfig().resolve_api_key()


def test_env_overrides_model(monkeypatch, config):
    monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-M2.7-highspeed")
    assert LLMConfig.from_config(config).model == "MiniMax-M2.7-highspeed"


# ---------- 端到端（不联网） ----------

def test_extract_from_text_end_to_end(config):
    transport, _ = fake_transport()
    result = extract_from_text("已知二次函数 y=3x2+6x-2，求它的最小值。", config, transport=transport)
    assert result.question.knowledge_points[0] == "二次函数"
    assert result.question.math_structure.effective_type == "quadratic_function"
    assert result.question.math_structure.normalized == "y=c+c*x^1+c*x^2"  # 数字被抹掉
    assert result.warnings == []


def test_extract_rejects_useless_model_output(config):
    transport, _ = fake_transport(body=_anthropic_body('{"difficulty": 3}'))
    with pytest.raises(ValueError, match="可比较的字段"):
        extract_from_text("看不清的题", config, transport=transport)


def test_extract_rejects_empty_text(config):
    transport, _ = fake_transport()
    with pytest.raises(ValueError, match="OCR 没有识别出任何文字"):
        extract_from_text("   ", config, transport=transport)


# ---------- OCR ----------

def test_clean_question_text_strips_leading_index():
    assert clean_question_text("3. 已知 y=x^2，\n求最小值。") == "已知 y=x^2， 求最小值。"
    assert clean_question_text("（12）求最值") == "求最值"


@pytest.mark.skipif("vision" not in available_backends(), reason="需要 macOS Vision (pip install ocrmac)")
def test_vision_ocr_reads_chinese_math(tmp_path):
    from PIL import Image, ImageDraw, ImageFont

    path = tmp_path / "q.png"
    img = Image.new("RGB", (880, 120), "white")
    ImageDraw.Draw(img).text(
        (24, 34),
        "已知二次函数 y = x² - 4x + 7，求最小值。",
        font=ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 32),
        fill="black",
    )
    img.save(path)

    result = ocr_image(path, backend="vision")
    assert "二次函数" in result.text and "最小值" in result.text
    assert result.backend == "vision"
