"""多格式文档文本提取 — bytes → 可索引文本（Block E B3）。

支持 pdf / csv / docx / md / txt / png / jpg 等常用格式，
上传后自动构建知识图谱。图片无文本 → 元数据占位 chunk（可被文件名检索），
不引入重型视觉方案（与已删除的 CLIP 一致）。

依赖：
- pdf 解析：pypdf
- docx 解析：python-docx
- csv/tsv：Python 标准库 csv
"""

from __future__ import annotations

import csv
import io

from app.core.logger import get_logger

logger = get_logger("prd2tsd.multi_format_loader")

# 可入图的文件扩展名
SUPPORTED_EXTENSIONS = {".md", ".txt", ".csv", ".tsv", ".docx", ".pdf", ".png", ".jpg", ".jpeg"}

# 图片类扩展名（无文本，仅元数据占位）
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def get_ext(filename: str) -> str:
    """提取小写扩展名。

    Args:
        filename: 原始文件名。

    Returns:
        小写扩展名（含点），无扩展名时返回 ".bin"。
    """
    idx = filename.rfind(".")
    return filename[idx:].lower() if idx >= 0 else ".bin"


def is_indexable(filename: str) -> bool:
    """文件是否为可入图格式。

    Args:
        filename: 原始文件名。

    Returns:
        是否可入图。
    """
    return get_ext(filename) in SUPPORTED_EXTENSIONS


def extract_text(content: bytes, filename: str) -> str:
    """从文件字节内容提取可索引文本。

    Args:
        content: 文件字节数据。
        filename: 原始文件名（用于判断格式）。

    Returns:
        提取的文本（图片返回元数据占位文本）。

    Raises:
        ValueError: 不支持的格式或提取失败。
    """
    ext = get_ext(filename)

    if ext in IMAGE_EXTENSIONS:
        return _image_placeholder(filename, content)
    if ext in (".md", ".txt"):
        return content.decode("utf-8", errors="replace")
    if ext in (".csv", ".tsv"):
        return _extract_csv(content, ext)
    if ext == ".docx":
        return _extract_docx(content)
    if ext == ".pdf":
        return _extract_pdf(content)

    raise ValueError(f"不支持的格式: {ext}")


def _extract_csv(content: bytes, ext: str) -> str:
    """CSV/TSV → 每行转自然语言句子（仅行级文本转换）。

    Args:
        content: 文件字节数据。
        ext: 扩展名（.csv / .tsv）。

    Returns:
        每行一条自然语言记录的文本。
    """
    delimiter = "\t" if ext == ".tsv" else ","
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    lines: list[str] = []
    for row in reader:
        cells = [cell.strip() for cell in row if cell and cell.strip()]
        if cells:
            lines.append("记录: " + "，".join(cells) + "。")
    return "\n".join(lines)


def _extract_docx(content: bytes) -> str:
    """docx → 段落 + 表格文本。

    Args:
        content: 文件字节数据。

    Returns:
        段落与表格行文本。
    """
    from docx import Document

    doc = Document(io.BytesIO(content))
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if cells:
                parts.append("表格行: " + "，".join(cells))
    return "\n".join(parts)


def _extract_pdf(content: bytes) -> str:
    """pdf → 逐页提取文本。

    Args:
        content: 文件字节数据。

    Returns:
        逐页文本（每页标注页码）。
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"[第 {i} 页]\n{page_text.strip()}")
    return "\n\n".join(pages)


def _image_placeholder(filename: str, content: bytes) -> str:
    """图片 → 元数据占位 chunk（可被文件名检索）。

    Args:
        filename: 原始文件名。
        content: 文件字节数据。

    Returns:
        元数据占位文本。
    """
    ext = get_ext(filename)
    size_kb = len(content) / 1024
    return f"[图片: {filename}, 类型 {ext.lstrip('.')}, 大小 {size_kb:.1f}KB]"
