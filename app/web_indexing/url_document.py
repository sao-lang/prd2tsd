"""URL 文档服务 — 抓取 URL → SSRF 校验 → 建文档记录 → 入库检索。

Block E B2：URL 文档上传分析。复用 WebLoader 抓取，
将 Markdown 内容作为文档入库（file_type="url" + source_url 溯源），
使 URL 文档可按文件名/标题检索，并可被知识层索引。
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.document_management.models import DocumentUpdate, UploadResponse
from app.document_management.service import DocumentManagementService, document_service
from app.web_indexing.url_security import validate_url
from app.web_indexing.web_loader import WebLoader

logger = get_logger("prd2tsd.url_document")

# URL 文档允许的最大抓取内容大小（防止超大页面拖垮服务）
MAX_URL_CONTENT_BYTES = 20 * 1024 * 1024  # 20MB


class UrlDocumentService:
    """URL 文档服务 — 抓取 URL 并入库为可检索文档。"""

    def __init__(
        self,
        loader: WebLoader | None = None,
        docs: DocumentManagementService | None = None,
    ) -> None:
        """初始化 URL 文档服务。

        Args:
            loader: Web 加载器（可选，默认新建）。
            docs: 文档管理服务（可选，默认全局单例）。
        """
        self.loader = loader or WebLoader()
        self.docs = docs or document_service

    async def fetch_content(self, url: str) -> dict[str, Any]:
        """SSRF 校验并抓取 URL 内容（供分析/生成复用）。

        Args:
            url: 目标 URL。

        Returns:
            WebLoader.fetch 结果，额外含 "validated_url" 键（校验后的 URL）。

        Raises:
            ValueError: URL 非法或抓取失败。
        """
        validated = await asyncio.to_thread(validate_url, url)
        result = await self.loader.fetch(validated)
        if result.get("error"):
            raise ValueError(f"URL 抓取失败: {result['error']}")
        result["validated_url"] = validated
        return result

    async def ingest(
        self,
        db: AsyncSession,
        workspace_id: str,
        user_id: str,
        url: str,
        session_id: str | None = None,
        tags: list[str] | None = None,
        fetched: dict[str, Any] | None = None,
    ) -> UploadResponse:
        """抓取 URL 并创建文档记录。

        流程：SSRF 校验 → 抓取 → 内容校验 → 入库（file_type="url" + source_url）。
        可传入 `fetched`（fetch_content 的结果）复用已抓取内容，避免重复请求。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            user_id: 用户 ID。
            url: 目标 URL。
            session_id: 关联会话 ID（可选）。
            tags: 标签（可选）。
            fetched: 已抓取结果（可选，复用避免重复请求）。

        Returns:
            上传响应（含文档记录）。

        Raises:
            ValueError: 工作空间缺失 / 抓取失败 / 内容为空或过大 / URL 非法。
        """
        if not workspace_id:
            raise ValueError("缺少工作空间上下文，无法入库 URL 文档")

        # 1. SSRF 校验 + 抓取（可复用已抓取结果）
        if fetched is None:
            fetched = await self.fetch_content(url)
        validated = fetched.get("validated_url") or url

        # 2. 内容校验
        content = fetched.get("content") or fetched.get("text_content") or ""
        if not content.strip():
            raise ValueError("URL 内容为空，无法入库")
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_URL_CONTENT_BYTES:
            raise ValueError(
                f"URL 内容过大（>{MAX_URL_CONTENT_BYTES // (1024 * 1024)}MB），拒绝入库",
            )

        # 3. 入库（Markdown 内容，.md 扩展名）
        filename = _derive_filename(validated, fetched.get("title") or "")
        upload = await self.docs.upload(
            db,
            workspace_id,
            user_id,
            content_bytes,
            filename,
            session_id=session_id,
            tags=tags,
        )

        # 4. 标记 file_type="url" + 记录 source_url 溯源
        await self.docs.repository.update(
            db,
            upload.document.id,
            DocumentUpdate(file_type="url", source_url=validated),
        )

        logger.info("URL 文档已入库: url=%s doc=%s", validated, upload.document.id)
        return upload


def _derive_filename(url: str, title: str) -> str:
    """从 URL/标题派生存储文件名。

    Args:
        url: 目标 URL。
        title: 页面标题（可能为空）。

    Returns:
        存储文件名（含 .md 扩展名，最长 80 字符）。
    """
    base = "".join(c for c in title if c.isalnum() or c in "-_") if title else ""
    if not base:
        parsed = urlparse(url)
        base = parsed.netloc or "url-doc"
    base = base[:80] or "url-doc"
    return f"{base}.md"
