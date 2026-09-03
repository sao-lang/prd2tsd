"""文档管理模块单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_management.deduplication import DocumentDeduplicator
from app.document_management.models import DocumentCreate, DocumentUpdate
from app.document_management.preview import DocumentPreviewGenerator
from app.document_management.repository import DocumentRepository
from app.document_management.search import DocumentSearchService
from app.document_management.service import DocumentManagementService


class TestDocumentDeduplicator:
    """文档去重单元测试。"""

    def test_compute_hash(self) -> None:
        """验证 SHA-256 计算。"""
        dedup = DocumentDeduplicator()
        h1 = dedup.compute_hash(b"hello")
        h2 = dedup.compute_hash(b"hello")
        h3 = dedup.compute_hash(b"world")
        assert h1 == h2  # 相同内容相同哈希
        assert h1 != h3  # 不同内容不同哈希

    def test_is_duplicate(self) -> None:
        """验证去重判断。"""
        dedup = DocumentDeduplicator()
        h = dedup.compute_hash(b"test")
        assert dedup.is_duplicate(h, h) is True
        assert dedup.is_duplicate(None, h) is False
        assert dedup.is_duplicate("abc", h) is False


class TestDocumentRepository:
    """文档仓库单元测试。"""

    @pytest.mark.asyncio
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        """验证创建并获取文档。"""
        repo = DocumentRepository()
        doc = await repo.create(
            db_session, "ws-test", "user-test",
            DocumentCreate(
                original_filename="test.md",
                file_size=100,
                file_type="md",
                storage_path="path/to/test.md",
            ),
        )
        assert doc.original_filename == "test.md"
        assert doc.file_size == 100

        fetched = await repo.get(db_session, doc.id)
        assert fetched is not None
        assert fetched.id == doc.id

    @pytest.mark.asyncio
    async def test_soft_delete(self, db_session: AsyncSession) -> None:
        """验证软删除。"""
        repo = DocumentRepository()
        doc = await repo.create(
            db_session, "ws-del", "user-del",
            DocumentCreate(original_filename="del.md", file_size=50, file_type="md", storage_path="x"),
        )
        deleted = await repo.soft_delete(db_session, doc.id)
        assert deleted is True
        fetched = await repo.get(db_session, doc.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_get_by_hash(self, db_session: AsyncSession) -> None:
        """验证按哈希查找。"""
        repo = DocumentRepository()
        doc = await repo.create(
            db_session, "ws-hash", "user-hash",
            DocumentCreate(
                original_filename="hash.md", file_size=10, file_type="md",
                storage_path="x", file_hash="abc123",
            ),
        )
        found = await repo.get_by_hash(db_session, "ws-hash", "abc123")
        assert found is not None
        assert found.id == doc.id

        not_found = await repo.get_by_hash(db_session, "ws-hash", "nonexist")
        assert not_found is None

    @pytest.mark.asyncio
    async def test_update_persists_build_counts_and_clears_error(self) -> None:
        """入图完成时应保存实体/关系统计，并允许显式清空旧错误。"""
        repo = DocumentRepository()
        repo.get = AsyncMock(return_value=None)  # type: ignore[method-assign]
        db = MagicMock(spec=AsyncSession)
        db.execute = AsyncMock()

        await repo.update(
            db,
            "doc-1",
            DocumentUpdate(
                processing_status="indexed",
                processing_error=None,
                entity_count=2,
                relation_count=1,
            ),
        )

        statement = db.execute.await_args.args[0]
        params = statement.compile().params
        assert params["processing_status"] == "indexed"
        assert params["processing_error"] is None
        assert params["entity_count"] == 2
        assert params["relation_count"] == 1


class TestDocumentSearch:
    """文档搜索单元测试。"""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, db_session: AsyncSession) -> None:
        """验证空查询返回最近文档。"""
        svc = DocumentSearchService()
        results = await svc.search(db_session, "ws", "")
        assert isinstance(results, list)


class TestDocumentPreview:
    """文档预览单元测试。"""

    @pytest.mark.asyncio
    async def test_markdown_preview(self) -> None:
        """验证 Markdown 预览。"""
        preview = DocumentPreviewGenerator()
        result = await preview.generate("doc-1", "md", b"# Hello\n\nThis is a test.")
        assert result.text_preview is not None
        assert "# Hello" in result.text_preview

    @pytest.mark.asyncio
    async def test_csv_preview(self) -> None:
        """验证 CSV 预览（前 20 行）。"""
        lines = "\n".join([f"row{i},val{i}" for i in range(30)])
        content = f"header,col\n{lines}".encode()
        preview = DocumentPreviewGenerator()
        result = await preview.generate("doc-1", "csv", content)
        assert result.text_preview is not None
        assert result.text_preview.count("\n") <= 21  # header + 20 rows

    @pytest.mark.asyncio
    async def test_unsupported_type(self) -> None:
        """验证不支持类型的预览。"""
        preview = DocumentPreviewGenerator()
        result = await preview.generate("doc-1", "exe", b"binary")
        assert "[EXE 文件暂不支持预览]" in (result.text_preview or "")


class TestDocumentService:
    """文档服务单元测试。"""

    @pytest.mark.asyncio
    async def test_upload_rejects_large_file(self) -> None:
        """验证过大文件被拒绝。"""
        svc = DocumentManagementService()
        large_content = b"x" * (51 * 1024 * 1024)
        with pytest.raises(ValueError, match="文件过大"):
            await svc.upload(None, "ws", "user", large_content, "test.md")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_upload_rejects_unsupported_type(self) -> None:
        """验证不支持的文件类型被拒绝。"""
        svc = DocumentManagementService()
        with pytest.raises(ValueError, match="不支持的文件类型"):
            await svc.upload(None, "ws", "user", b"data", "test.exe")  # type: ignore[arg-type]

    def test_get_ext(self) -> None:
        """验证扩展名提取。"""
        assert DocumentManagementService._get_ext("file.md") == ".md"
        assert DocumentManagementService._get_ext("file.CSV") == ".csv"
        assert DocumentManagementService._get_ext("file") == ".bin"
