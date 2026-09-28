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

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import pdfplumber


@dataclass
class PageText:
    page: int
    text: str
    char_count: int
    is_blank: bool


@dataclass
class PdfExtractResult:
    source: str
    page_count: int
    pages: List[PageText]
    total_chars: int
    blank_pages: List[int]
    backend: str = "pdfplumber"

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "backend": self.backend,
            "page_count": self.page_count,
            "total_chars": self.total_chars,
            "blank_pages": self.blank_pages,
            "pages": [asdict(p) for p in self.pages],
        }


class PdfExtractError(RuntimeError):
    pass


def _extract_one(pdf_path: Path) -> PdfExtractResult:
    if not pdf_path.exists():
        raise PdfExtractError(f"PDF 不存在: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PdfExtractError(f"不是 PDF 文件: {pdf_path}")

    pages: List[PageText] = []
    blank: List[int] = []

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            page_count = len(pdf.pages)
            for idx, page in enumerate(pdf.pages, start=1):
                raw = page.extract_text() or ""
                text = raw.strip()
                is_blank = len(text) == 0
                if is_blank:
                    blank.append(idx)
                pages.append(
                    PageText(
                        page=idx,
                        text=text,
                        char_count=len(text),
                        is_blank=is_blank,
                    )
                )
    except Exception as exc:  # pdfplumber 抛的异常类型不一,这里统一包一层
        raise PdfExtractError(f"读取 PDF 失败 {pdf_path.name}: {exc}") from exc

    total = sum(p.char_count for p in pages)
    return PdfExtractResult(
        source=str(pdf_path),
        page_count=page_count,
        pages=pages,
        total_chars=total,
        blank_pages=blank,
    )


def extract_pdf(pdf_path: str | Path) -> PdfExtractResult:
    return _extract_one(Path(pdf_path))


def iter_pdfs(inputs: Iterable[Path]) -> Iterable[Path]:
    for p in inputs:
        if p.is_dir():
            yield from sorted(p.glob("*.pdf"))
        elif p.suffix.lower() == ".pdf":
            yield p
        else:
            print(f"[skip] 不是 PDF: {p}", file=sys.stderr)


def render_text(result: PdfExtractResult) -> str:
    """把整本 PDF 渲染成一段文本,每页用页码分隔,方便直接看。"""
    chunks = []
    for p in result.pages:
        chunks.append(f"\n===== page {p.page} =====\n")
        chunks.append(p.text)
        chunks.append("\n")
    return "".join(chunks).strip() + "\n"


def write_text(result: PdfExtractResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_text(result), encoding="utf-8")


def write_json(result: PdfExtractResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agents.pdf_to_text",
        description="第一步:PDF → 纯文本(pdfplumber)",
    )
    p.add_argument(
        "inputs",
        nargs="+",
        help="一个或多个 PDF 文件 / 包含 PDF 的目录",
    )
    p.add_argument(
        "-o", "--output",
        help="单个 PDF 时的输出文本文件路径",
    )
    p.add_argument(
        "--out-dir",
        help="批量模式输出目录;文件名沿用 <原名>.txt",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="同时输出 JSON 结构(含每页元信息)",
    )
    p.add_argument(
        "--quiet", action="store_true", help="不打印进度",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    inputs = [Path(x) for x in args.inputs]
    pdfs = list(iter_pdfs(inputs))
    if not pdfs:
        print("[error] 没找到任何 PDF", file=sys.stderr)
        return 2

    if len(pdfs) == 1 and args.output:
        out_dir = None
        single_out = Path(args.output)
    elif args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        single_out = None
    elif len(pdfs) == 1:
        single_out = pdfs[0].with_suffix(".txt")
        out_dir = None
    else:
        print("[error] 多个 PDF 时必须指定 --out-dir 或逐个用 -o", file=sys.stderr)
        return 2

    failed = 0
    for pdf in pdfs:
        if not args.quiet:
            print(f"[pdf→text] {pdf}", file=sys.stderr)
        try:
            result = extract_pdf(pdf)
        except PdfExtractError as exc:
            print(f"[fail] {exc}", file=sys.stderr)
            failed += 1
            continue

        if single_out is not None:
            target = single_out
        else:
            assert out_dir is not None
            target = out_dir / f"{pdf.stem}.txt"
        write_text(result, target)
        if args.json:
            write_json(result, target.with_suffix(".json"))

        if not args.quiet:
            note = ""
            if result.blank_pages:
                note = f" (空页: {result.blank_pages})"
            print(
                f"  → {target}  pages={result.page_count}  chars={result.total_chars}{note}",
                file=sys.stderr,
            )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
