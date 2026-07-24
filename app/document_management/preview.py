"""文档预览生成 — Markdown/PDF/CSV 预览。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.document_management.models import PreviewResult

logger = get_logger("prd2tsd.document_preview")


class DocumentPreviewGenerator:
    """文档预览生成器。

    按文件类型生成预览内容。
    """

    MAX_PREVIEW_CHARS = 5000

    async def generate(
        self,
        document_id: str,
        file_type: str,
        content: bytes,
    ) -> PreviewResult:
        """生成文档预览。

        Args:
            document_id: 文档 ID。
            file_type: 文件类型。
            content: 文件内容。

        Returns:
            预览结果。
        """
        try:
            if file_type == "md":
                return await self._preview_markdown(document_id, content)
            if file_type == "txt":
                return await self._preview_text(document_id, content)
            if file_type == "csv":
                return await self._preview_csv(document_id, content)
            if file_type == "pdf":
                return await self._preview_pdf(document_id, content)
            if file_type in ("png", "jpg", "jpeg"):
                return await self._preview_image(document_id, file_type)
            return PreviewResult(
                document_id=document_id,
                file_type=file_type,
                text_preview=f"[{file_type.upper()} 文件暂不支持预览]",
            )
        except Exception as exc:
            logger.warning("预览生成失败: %s - %s", document_id, exc)
            return PreviewResult(
                document_id=document_id,
                file_type=file_type,
                error=str(exc),
            )

    async def _preview_markdown(
        self,
        document_id: str,
        content: bytes,
    ) -> PreviewResult:
        """生成 Markdown 预览。"""
        text = content.decode("utf-8", errors="replace")
        return PreviewResult(
            document_id=document_id,
            file_type="md",
            text_preview=text[:self.MAX_PREVIEW_CHARS],
            page_count=text.count("\n## ") + 1,
        )

    async def _preview_text(
        self,
        document_id: str,
        content: bytes,
    ) -> PreviewResult:
        """生成纯文本预览。"""
        text = content.decode("utf-8", errors="replace")
        return PreviewResult(
            document_id=document_id,
            file_type="txt",
            text_preview=text[:self.MAX_PREVIEW_CHARS],
        )

    async def _preview_csv(
        self,
        document_id: str,
        content: bytes,
    ) -> PreviewResult:
        """生成 CSV 预览（前 20 行表格）。"""
        text = content.decode("utf-8", errors="replace")
        lines = text.splitlines()
        preview_lines = lines[:21]  # header + 20 rows
        preview = "\n".join(preview_lines)
        return PreviewResult(
            document_id=document_id,
            file_type="csv",
            text_preview=preview,
            page_count=len(lines),
        )

    async def _preview_pdf(
        self,
        document_id: str,
        content: bytes,
    ) -> PreviewResult:
        """生成 PDF 预览（占位）。"""
        return PreviewResult(
            document_id=document_id,
            file_type="pdf",
            text_preview=f"[PDF 文件，大小 {len(content)} 字节]",
            page_count=0,
        )

    async def _preview_image(
        self,
        document_id: str,
        file_type: str,
    ) -> PreviewResult:
        """生成图片预览（占位）。"""
        return PreviewResult(
            document_id=document_id,
            file_type=file_type,
            text_preview=f"[{file_type.upper()} 图片文件]",
        )
