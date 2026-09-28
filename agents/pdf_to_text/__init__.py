"""第一步 agent:把 PDF 转成纯文本。

只做一件事:输入 PDF 路径,输出每页的文字。
后续步骤(题目切分、字段抽取、打分匹配)由别的 agent 接。

支持两种输入:
- 文本型 PDF:pdfplumber 直接抽,质量最好,优先走这条路
- 扫描型 PDF:pdfplumber 抽出来是空的,后续步骤可以接 OCR(本步不实现)

CLI 用法:
    python -m agents.pdf_to_text data/raw/foo.pdf -o data/text/foo.txt
    python -m agents.pdf_to_text data/raw/ --out-dir data/text/
"""

from .extract import (
    PageText,
    PdfExtractError,
    PdfExtractResult,
    extract_pdf,
    iter_pdfs,
    main,
    render_text,
    write_json,
    write_text,
)

__all__ = [
    "PageText",
    "PdfExtractError",
    "PdfExtractResult",
    "extract_pdf",
    "iter_pdfs",
    "main",
    "render_text",
    "write_json",
    "write_text",
]
