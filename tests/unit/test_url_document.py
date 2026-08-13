"""URL 文档服务（抓取 → 入库）单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.document_management.models import DocumentOut, DocumentUpdate, UploadResponse
from app.web_indexing.url_document import UrlDocumentService, _derive_filename


def _fake_upload(doc_id: str = "doc-1") -> UploadResponse:
    """构造伪上传响应。"""
    return UploadResponse(
        document=DocumentOut(
            id=doc_id,
            workspace_id="ws-1",
            user_id="user-1",
            original_filename="Title.md",
            file_size=100,
            file_type="url",
            source_url="https://example.com/doc",
        ),
        deduplicated=False,
    )


class TestUrlDocumentService:
    """UrlDocumentService 单元测试（mock loader 与文档服务）。"""

    def _make_service(self, fetch_result: dict | None = None) -> tuple[UrlDocumentService, MagicMock, MagicMock]:
        """构造服务与 mock。"""
        loader = MagicMock()
        loader.fetch = AsyncMock(return_value=fetch_result or {
            "url": "https://example.com/doc",
            "title": "Example Doc",
            "content": "# Example\n正文内容",
            "text_content": "Example\n正文内容",
            "error": None,
        })
        docs = MagicMock()
        docs.upload = AsyncMock(return_value=_fake_upload())
        repo = MagicMock()
        repo.update = AsyncMock(return_value=None)
        docs.repository = repo
        return UrlDocumentService(loader=loader, docs=docs), loader, docs

    @pytest.mark.asyncio
    async def test_ingest_uploads_and_sets_source_url(self) -> None:
        """验证正常抓取入库并标记 source_url + file_type=url。"""
        svc, loader, docs = self._make_service()
        result = await svc.ingest(
            db=object(),  # type: ignore[arg-type]
            workspace_id="ws-1",
            user_id="user-1",
            url="https://example.com/doc",
        )

        loader.fetch.assert_awaited_once()
        # 上传内容为 Markdown（workspace_id/user_id/content 为位置参数）
        call_args = docs.upload.await_args
        assert call_args is not None
        assert call_args.args[1] == "ws-1"
        assert call_args.args[2] == "user-1"
        assert b"# Example" in call_args.args[3]  # content bytes

        # source_url + file_type 更新
        update_call = docs.repository.update.await_args
        assert update_call is not None
        update_data: DocumentUpdate = (
            update_call.kwargs["data"]
            if "data" in update_call.kwargs
            else update_call.args[2]
        )
        assert update_data.source_url == "https://example.com/doc"
        assert update_data.file_type == "url"

        assert result.document.id == "doc-1"

    @pytest.mark.asyncio
    async def test_ingest_rejects_missing_workspace(self) -> None:
        """验证缺少工作空间时拒绝。"""
        svc, _, docs = self._make_service()
        with pytest.raises(ValueError, match="工作空间"):
            await svc.ingest(
                db=object(),  # type: ignore[arg-type]
                workspace_id="",
                user_id="user-1",
                url="https://example.com/doc",
            )
        docs.upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ingest_rejects_ssrf_url(self) -> None:
        """验证 SSRF 内网 URL 在抓取前被拦截。"""
        svc, loader, docs = self._make_service()
        with pytest.raises(ValueError, match="禁止访问本机|禁止访问内网"):
            await svc.ingest(
                db=object(),  # type: ignore[arg-type]
                workspace_id="ws-1",
                user_id="user-1",
                url="http://127.0.0.1/x",
            )
        loader.fetch.assert_not_awaited()
        docs.upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ingest_raises_on_fetch_error(self) -> None:
        """验证抓取失败时抛错。"""
        svc, _, docs = self._make_service({"url": "https://e.com", "error": "请求超时"})
        with pytest.raises(ValueError, match="抓取失败"):
            await svc.ingest(
                db=object(),  # type: ignore[arg-type]
                workspace_id="ws-1",
                user_id="user-1",
                url="https://example.com/doc",
            )
        docs.upload.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ingest_rejects_empty_content(self) -> None:
        """验证内容为空时拒绝入库。"""
        svc, _, docs = self._make_service({
            "url": "https://example.com/doc", "title": "", "content": "  ", "text_content": "", "error": None,
        })
        with pytest.raises(ValueError, match="内容为空"):
            await svc.ingest(
                db=object(),  # type: ignore[arg-type]
                workspace_id="ws-1",
                user_id="user-1",
                url="https://example.com/doc",
            )
        docs.upload.assert_not_awaited()

    def test_derive_filename_from_title(self) -> None:
        """验证从标题派生文件名。"""
        assert _derive_filename("https://example.com/doc", "Example Doc") == "ExampleDoc.md"

    def test_derive_filename_from_host(self) -> None:
        """验证无标题时从主机名派生文件名。"""
        assert _derive_filename("https://example.com/long/path", "") == "example.com.md"
