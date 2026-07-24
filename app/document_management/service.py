"""文档管理服务 — 上传/列表/预览/搜索/删除/CSV 索引。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.document_management.csv_loader import CsvDualPathIndexer
from app.document_management.deduplication import DocumentDeduplicator
from app.document_management.models import (
    DocumentCreate,
    DocumentOut,
    DocumentStats,
    DocumentUpdate,
    PreviewResult,
    SearchResult,
    UploadResponse,
)
from app.document_management.preview import DocumentPreviewGenerator
from app.document_management.repository import DocumentRepository
from app.document_management.search import DocumentSearchService
from app.document_management.storage import DocumentStorage

logger = get_logger("prd2tsd.document_service")

# 允许上传的文件类型
ALLOWED_EXTENSIONS = {".md", ".pdf", ".docx", ".txt", ".csv", ".tsv", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class DocumentManagementService:
    """文档管理服务 — 统一对外接口。"""

    def __init__(
        self,
        repository: DocumentRepository | None = None,
        storage: DocumentStorage | None = None,
        deduplicator: DocumentDeduplicator | None = None,
        preview: DocumentPreviewGenerator | None = None,
        search_service: DocumentSearchService | None = None,
        csv_indexer: CsvDualPathIndexer | None = None,
    ) -> None:
        """初始化文档管理服务。

        Args:
            repository: 文档仓库。
            storage: 文档存储后端。
            deduplicator: 去重器。
            preview: 预览生成器。
            search_service: 搜索服务。
            csv_indexer: CSV 索引器。
        """
        self.repository = repository or DocumentRepository()
        self.storage = storage or DocumentStorage()
        self.deduplicator = deduplicator or DocumentDeduplicator()
        self.preview = preview or DocumentPreviewGenerator()
        self.search_service = search_service or DocumentSearchService()
        self.csv_indexer = csv_indexer or CsvDualPathIndexer()

    async def upload(
        self,
        db: AsyncSession,
        workspace_id: str,
        user_id: str,
        content: bytes,
        filename: str,
        session_id: str | None = None,
        tags: list[str] | None = None,
    ) -> UploadResponse:
        """上传文档。

        流程：校验 → 去重 → 存 MinIO → 写 DB → CSV 索引。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            user_id: 用户 ID。
            content: 文件字节数据。
            filename: 原始文件名。
            session_id: 关联会话 ID。
            tags: 标签。

        Returns:
            上传响应（含去重标记）。

        Raises:
            ValueError: 文件类型不支持或文件过大。
        """
        # 校验文件类型
        ext = self._get_ext(filename)
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的文件类型: {ext}，仅支持: {sorted(ALLOWED_EXTENSIONS)}")

        # 校验文件大小
        if len(content) > MAX_FILE_SIZE:
            raise ValueError(f"文件过大: {len(content)} 字节（最大 {MAX_FILE_SIZE} 字节）")

        # 计算哈希 + 去重
        file_hash = self.deduplicator.compute_hash(content)
        existing = await self.repository.get_by_hash(db, workspace_id, file_hash)
        if existing:
            logger.info("文件重复上传（哈希: %s），返回已有记录", file_hash[:12])
            return UploadResponse(document=existing, deduplicated=True)

        # 存储到 MinIO
        upload_result = await self.storage.upload(workspace_id, content, filename)

        # 创建数据库记录
        file_type = ext.lstrip(".")
        doc_data = DocumentCreate(
            original_filename=filename,
            file_size=upload_result["file_size"],
            file_type=file_type,
            mime_type=upload_result.get("mime_type"),
            file_hash=upload_result["file_hash"],
            storage_path=upload_result["storage_path"],
            session_id=session_id,
            tags=tags,
        )
        doc = await self.repository.create(db, workspace_id, user_id, doc_data)

        # CSV 双通路索引
        if file_type in ("csv", "tsv"):
            try:
                index_result = await self.csv_indexer.process(content, filename, doc.id)
                await self.repository.update(
                    db, doc.id,
                    DocumentUpdate(processing_status="indexed"),
                )
                logger.info("CSV 索引完成: %s", index_result.get("row_count", 0))
            except Exception as exc:
                logger.warning("CSV 索引失败: %s", exc)
                await self.repository.update(
                    db, doc.id,
                    DocumentUpdate(processing_status="failed", processing_error=str(exc)),
                )

        return UploadResponse(document=doc, deduplicated=False)

    async def get_document(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> DocumentOut | None:
        """获取文档信息。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。

        Returns:
            文档信息。
        """
        return await self.repository.get(db, document_id)

    async def list_documents(
        self,
        db: AsyncSession,
        workspace_id: str,
        page: int = 1,
        page_size: int = 20,
        file_type: str | None = None,
        status: str | None = None,
        sort_by: str = "created_at",
    ) -> tuple[list[DocumentOut], int]:
        """列出文档。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            page: 页码。
            page_size: 每页条数。
            file_type: 文件类型筛选。
            status: 处理状态筛选。
            sort_by: 排序字段。

        Returns:
            (文档列表, 总数)。
        """
        return await self.repository.list_documents(
            db, workspace_id, page, page_size, file_type, status, sort_by,
        )

    async def delete_document(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> bool:
        """删除文档（软删除 + 从 MinIO 删除）。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。

        Returns:
            是否删除成功。
        """
        doc = await self.repository.get(db, document_id)
        if doc is None:
            return False

        # 从 MinIO 删除
        if doc.storage_path:
            await self.storage.delete(doc.storage_path)

        # 软删除 DB 记录
        return await self.repository.soft_delete(db, document_id)

    async def get_preview(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> PreviewResult:
        """获取文档预览。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。

        Returns:
            预览结果。
        """
        doc = await self.repository.get(db, document_id)
        if doc is None:
            return PreviewResult(
                document_id=document_id, file_type="", error="文档不存在",
            )

        try:
            content = await self.storage.download(doc.storage_path)
        except Exception as exc:
            return PreviewResult(
                document_id=document_id,
                file_type=doc.file_type,
                error=f"下载失败: {exc}",
            )

        return await self.preview.generate(document_id, doc.file_type, content)

    async def search_documents(
        self,
        db: AsyncSession,
        workspace_id: str,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SearchResult]:
        """搜索文档。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            query: 搜索关键词。
            page: 页码。
            page_size: 每页条数。

        Returns:
            搜索结果。
        """
        return await self.search_service.search(db, workspace_id, query, page, page_size)

    async def get_stats(
        self,
        db: AsyncSession,
        workspace_id: str,
    ) -> DocumentStats:
        """获取文档统计。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。

        Returns:
            文档统计。
        """
        return await self.repository.get_stats(db, workspace_id)

    async def reindex(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> bool:
        """重索引文档。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。

        Returns:
            是否成功触发重索引。
        """
        doc = await self.repository.get(db, document_id)
        if doc is None:
            return False
        await self.repository.update(
            db, document_id,
            DocumentUpdate(processing_status="pending", processing_error=None),
        )
        return True

    @staticmethod
    def _get_ext(filename: str) -> str:
        idx = filename.rfind(".")
        return filename[idx:].lower() if idx >= 0 else ".bin"


# 全局单例
document_service = DocumentManagementService()
