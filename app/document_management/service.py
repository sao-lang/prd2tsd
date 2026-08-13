"""文档管理服务 — 上传/列表/预览/搜索/删除。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
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


def _trigger_kg_index(document_id: str) -> bool:
    """触发文档入图 Celery 任务；Celery 不可用时降级跳过。

    Args:
        document_id: 文档 ID。

    Returns:
        是否成功触发。
    """
    try:
        from app.batch.tasks import celery_app, index_document_to_kg

        if celery_app is None:
            logger.warning("Celery 未安装，跳过文档入图: %s", document_id)
            return False
        index_document_to_kg.delay(document_id)
        logger.info("已触发文档入图任务: %s", document_id)
        return True
    except Exception as exc:
        logger.warning("触发文档入图失败: %s - %s", document_id, exc)
        return False


class DocumentManagementService:
    """文档管理服务 — 统一对外接口。"""

    def __init__(
        self,
        repository: DocumentRepository | None = None,
        storage: DocumentStorage | None = None,
        deduplicator: DocumentDeduplicator | None = None,
        preview: DocumentPreviewGenerator | None = None,
        search_service: DocumentSearchService | None = None,
    ) -> None:
        """初始化文档管理服务。

        Args:
            repository: 文档仓库。
            storage: 文档存储后端。
            deduplicator: 去重器。
            preview: 预览生成器。
            search_service: 搜索服务。
        """
        self.repository = repository or DocumentRepository()
        self.storage = storage or DocumentStorage()
        self.deduplicator = deduplicator or DocumentDeduplicator()
        self.preview = preview or DocumentPreviewGenerator()
        self.search_service = search_service or DocumentSearchService()

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

        流程：校验 → 去重 → 存 MinIO → 写 DB。

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

        # Block E B3: 多格式文档自动入图（异步 Celery 任务）
        from app.knowledge_layer.ingestion.multi_format_loader import is_indexable

        if is_indexable(filename):
            await self.repository.update(
                db, doc.id,
                DocumentUpdate(processing_status="pending", processing_error=None),
            )
            _trigger_kg_index(doc.id)

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

    async def get_document_content(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> tuple[bytes, str] | None:
        """获取文档原始内容与原始文件名（供文档分析/入图复用）。

        与 get_preview 不同，此方法返回未经预览截断的原始字节，
        供 `multi_format_loader.extract_text` 按格式完整提取文本，
        避免 PDF/docx 分析读取预览占位文本（Block E B1 断点修复）。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。

        Returns:
            (原始字节, 原始文件名)；文档不存在或无存储路径时返回 None。
        """
        doc = await self.repository.get(db, document_id)
        if doc is None or not doc.storage_path:
            return None
        content = await self.storage.download(doc.storage_path)
        return content, doc.original_filename

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
