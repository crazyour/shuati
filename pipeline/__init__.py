"""图片 -> OCR -> MiniMax -> 题目 JSON 的提取流水线。

和 mqm/ 是分开的：mqm 只做匹配，不依赖 OCR 和网络。
"""

from .extract import ExtractResult, extract_from_image, extract_from_text, normalize_question_json
from .llm import LLMConfig, LLMError, LLMHTTPError, LLMOutputError, MissingAPIKeyError, complete
from .ocr import OcrError, OcrResult, available_backends, ocr_image

__all__ = [
    "ExtractResult",
    "extract_from_image",
    "extract_from_text",
    "normalize_question_json",
    "LLMConfig",
    "LLMError",
    "LLMHTTPError",
    "LLMOutputError",
    "MissingAPIKeyError",
    "complete",
    "OcrError",
    "OcrResult",
    "available_backends",
    "ocr_image",
]
