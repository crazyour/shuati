"""图片 OCR。默认用 macOS 自带的 Vision 框架（离线、中文好、不用下模型）。"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

DEFAULT_LANGUAGES = ("zh-Hans", "en-US")

# tesseract 的语言代码和 Vision 不一样，这里做个映射
_TESSERACT_LANGS = {"zh-Hans": "chi_sim", "zh-Hant": "chi_tra", "en-US": "eng", "ja-JP": "jpn"}


class OcrError(RuntimeError):
    pass


@dataclass
class OcrResult:
    text: str
    lines: List[Tuple[str, float]]  # (文本, 置信度)
    backend: str

    @property
    def confidence(self) -> Optional[float]:
        """所有行置信度的均值；Vision 对中文给的分数普遍偏低，只当参考。"""
        if not self.lines:
            return None
        return sum(conf for _, conf in self.lines) / len(self.lines)


def available_backends() -> List[str]:
    backends = []
    if platform.system() == "Darwin":
        try:
            import ocrmac  # noqa: F401

            backends.append("vision")
        except ImportError:
            pass
    if shutil.which("tesseract"):
        backends.append("tesseract")
    return backends


def _ocr_vision(path: Path, languages: Sequence[str]) -> OcrResult:
    try:
        from ocrmac import ocrmac
    except ImportError as exc:  # pragma: no cover - 依赖缺失时才走到
        raise OcrError("缺少 ocrmac：pip install ocrmac") from exc

    try:
        raw = ocrmac.OCR(str(path), language_preference=list(languages)).recognize()
    except Exception as exc:  # Vision 的报错类型不稳定，统一包一层
        raise OcrError(f"Vision OCR 失败：{exc}") from exc

    # bbox 是 (x, y, w, h)，原点在左下 -> 先按 y 从大到小（从上往下），再按 x 从左到右
    ordered = sorted(raw, key=lambda item: (-round(item[2][1], 2), item[2][0]))
    lines = [(text.strip(), float(conf)) for text, conf, _ in ordered if text.strip()]
    return OcrResult(text="\n".join(t for t, _ in lines), lines=lines, backend="vision")


def _ocr_tesseract(path: Path, languages: Sequence[str]) -> OcrResult:
    langs = [_TESSERACT_LANGS.get(lang, lang) for lang in languages]
    installed = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True
    ).stdout.splitlines()
    missing = [lang for lang in langs if lang not in installed]
    if missing:
        raise OcrError(
            f"tesseract 缺少语言包 {', '.join(missing)}：brew install tesseract-lang"
        )

    proc = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "+".join(langs)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise OcrError(f"tesseract 失败：{proc.stderr.strip()[:200]}")
    lines = [(line.strip(), 1.0) for line in proc.stdout.splitlines() if line.strip()]
    return OcrResult(text="\n".join(t for t, _ in lines), lines=lines, backend="tesseract")


def ocr_image(
    path: str | Path,
    backend: str = "auto",
    languages: Sequence[str] = DEFAULT_LANGUAGES,
) -> OcrResult:
    """backend: auto | vision | tesseract"""
    path = Path(path)
    if not path.exists():
        raise OcrError(f"图片不存在：{path}")

    if backend == "auto":
        candidates = available_backends()
        if not candidates:
            raise OcrError(
                "没有可用的 OCR 后端。macOS 装 ocrmac（pip install ocrmac），"
                "或装 tesseract（brew install tesseract tesseract-lang）。"
            )
        backend = candidates[0]

    if backend == "vision":
        return _ocr_vision(path, languages)
    if backend == "tesseract":
        return _ocr_tesseract(path, languages)
    raise OcrError(f"未知 OCR 后端：{backend!r}（支持 auto / vision / tesseract）")


_LEADING_INDEX_RE = re.compile(r"^\s*(?:[（(]?\d{1,2}[）)．.、]|[一二三四五六七八九十]+[、.])\s*")


def clean_question_text(text: str) -> str:
    """去掉行首题号、压掉多余空白。只用于展示，喂给模型的仍是原始 OCR 文本。"""
    lines = [_LEADING_INDEX_RE.sub("", line).strip() for line in text.splitlines()]
    return " ".join(line for line in lines if line)
