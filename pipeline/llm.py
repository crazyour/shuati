"""MiniMax 客户端。

默认按 Anthropic Messages 格式发（~/.minimax/config.yaml 里那个网关用的是 @ai-sdk/anthropic），
换成 OpenAI 兼容端点时把 config 里的 api_style 改成 "openai" 即可。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

# transport(url, headers, payload, timeout) -> (status_code, 响应体)
Transport = Callable[[str, Dict[str, str], Dict[str, Any], float], Tuple[int, Any]]


class LLMError(RuntimeError):
    pass


class MissingAPIKeyError(LLMError):
    pass


class LLMHTTPError(LLMError):
    pass


class LLMOutputError(LLMError):
    pass


def load_env_file(path: Path = ENV_FILE) -> None:
    """读项目根目录的 .env（KEY=VALUE），不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass
class LLMConfig:
    base_url: str = "https://agent.minimaxi.com/mavis/api/v1/llm/v1"
    model: str = "MiniMax-M2.7"
    api_style: str = "anthropic"  # anthropic | openai
    max_tokens: int = 4096
    temperature: Optional[float] = None  # 不填就不发，避免和"强制思考"的模型冲突
    timeout: float = 120.0
    api_key_env: str = "MINIMAX_API_KEY"
    api_key: Optional[str] = None

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None) -> "LLMConfig":
        section = dict((config or {}).get("llm", {}))
        known = {f: section[f] for f in cls.__dataclass_fields__ if f in section}
        cfg = cls(**known)
        # 环境变量优先，方便临时切模型/切端点
        cfg.base_url = os.environ.get("MINIMAX_BASE_URL", cfg.base_url)
        cfg.model = os.environ.get("MINIMAX_MODEL", cfg.model)
        cfg.api_style = os.environ.get("MINIMAX_API_STYLE", cfg.api_style)
        return cfg

    def resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        load_env_file()
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise MissingAPIKeyError(
                f"没有找到 API key。请设置环境变量 {self.api_key_env}，"
                f"或在项目根目录建一个 .env 文件写上 {self.api_key_env}=你的key"
                f"（可以复制 .env.example）。"
            )
        return key

    @property
    def endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/messages" if self.api_style == "anthropic" else f"{base}/chat/completions"


def _requests_transport(
    url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float
) -> Tuple[int, Any]:
    import requests  # 延迟导入：不用 LLM 的场景不需要这个依赖

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise LLMHTTPError(f"请求 {url} 失败：{exc}") from exc
    try:
        return res.status_code, res.json()
    except ValueError:
        return res.status_code, res.text


def _build_request(system: str, user: str, cfg: LLMConfig) -> Tuple[Dict[str, str], Dict[str, Any]]:
    key = cfg.resolve_api_key()

    if cfg.api_style == "anthropic":
        # 网关的鉴权头不确定是哪种，两个都带上
        headers = {
            "content-type": "application/json",
            "x-api-key": key,
            "authorization": f"Bearer {key}",
            "anthropic-version": "2023-06-01",
        }
        payload: Dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
    elif cfg.api_style == "openai":
        headers = {"content-type": "application/json", "authorization": f"Bearer {key}"}
        payload = {
            "model": cfg.model,
            "max_tokens": cfg.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    else:
        raise LLMError(f"未知 api_style：{cfg.api_style!r}（支持 anthropic / openai）")

    if cfg.temperature is not None:
        payload["temperature"] = cfg.temperature
    return headers, payload


def _extract_text(data: Any, cfg: LLMConfig) -> str:
    """从响应里取出文本。M2.7 强制思考，返回里会混 thinking 块，要跳过。"""
    if not isinstance(data, dict):
        raise LLMOutputError(f"响应不是 JSON 对象：{str(data)[:300]}")

    if cfg.api_style == "anthropic":
        blocks = data.get("content") or []
        texts = [
            b.get("text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
        ]
        if texts:
            return "\n".join(texts)
        raise LLMOutputError(
            f"响应里没有 text 块（stop_reason={data.get('stop_reason')}）：{json.dumps(data, ensure_ascii=False)[:400]}"
        )

    choices = data.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content:
            return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    raise LLMOutputError(f"响应里没有 content：{json.dumps(data, ensure_ascii=False)[:400]}")


def complete(
    system: str, user: str, config: Optional[LLMConfig] = None, transport: Optional[Transport] = None
) -> str:
    cfg = config or LLMConfig()
    headers, payload = _build_request(system, user, cfg)
    status, data = (transport or _requests_transport)(cfg.endpoint, headers, payload, cfg.timeout)

    if status >= 400:
        detail = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        hint = ""
        if status in (401, 403):
            hint = f"（{cfg.api_key_env} 是不是没设对？）"
        elif status == 404:
            hint = f"（base_url 或 model 可能不对：{cfg.endpoint} / {cfg.model}）"
        return_msg = f"{cfg.model} 返回 HTTP {status}{hint}：{detail[:500]}"
        raise LLMHTTPError(return_msg)

    return _extract_text(data, cfg)


def extract_json_object(text: str) -> Dict[str, Any]:
    """从模型输出里抠出第一个 JSON 对象。带 ``` 围栏或前后有废话都能处理。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if "```" in stripped:
            stripped = stripped.rsplit("```", 1)[0]
        stripped = stripped.strip()

    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    if start == -1:
        raise LLMOutputError(f"模型没有输出 JSON：{text[:300]}")

    depth, in_string, escaped = 0, False, False
    for i, ch in enumerate(stripped[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : i + 1]
                try:
                    data = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise LLMOutputError(f"模型输出的 JSON 解析失败：{exc.msg}\n{candidate[:300]}") from exc
                if not isinstance(data, dict):
                    raise LLMOutputError(f"模型输出的不是 JSON 对象：{candidate[:300]}")
                return data
    raise LLMOutputError(f"模型输出的 JSON 括号没闭合：{stripped[start:start + 300]}")
