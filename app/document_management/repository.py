"""文档数据库访问层。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_management.models import (
    DocumentCreate,
    DocumentOut,
    DocumentStats,
    DocumentUpdate,
)
from app.models.block_e import UploadedDocument


class DocumentRepository:
    """文档数据库访问层。"""

    ALLOWED_SORT_FIELDS = {"created_at", "file_size", "file_type", "processing_status"}

    async def create(
        self,
        db: AsyncSession,
        workspace_id: str,
        user_id: str,
        data: DocumentCreate,
    ) -> DocumentOut:
        """创建文档记录。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            user_id: 用户 ID。
            data: 文档数据。

        Returns:
            创建的文档信息。
        """
        doc = UploadedDocument(
            workspace_id=workspace_id,
            user_id=user_id,
            original_filename=data.original_filename,
            file_size=data.file_size,
            file_type=data.file_type,
            mime_type=data.mime_type,
            file_hash=data.file_hash,
            storage_path=data.storage_path,
            session_id=data.session_id,
            task_id=data.task_id,
            tags=data.tags or [],
        )
        db.add(doc)
        await db.flush()
        await db.refresh(doc)
        return self._to_out(doc)

    async def get(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> DocumentOut | None:
        """获取单个文档。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。

        Returns:
            文档信息，不存在时返回 None。
        """
        result = await db.execute(
            select(UploadedDocument).where(
                UploadedDocument.id == document_id,
                UploadedDocument.is_deleted.is_(False),
            ),
        )
        doc = result.scalar_one_or_none()
        return self._to_out(doc) if doc else None

    async def get_by_hash(
        self,
        db: AsyncSession,
        workspace_id: str,
        file_hash: str,
    ) -> DocumentOut | None:
        """按文件哈希查找文档（去重用）。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            file_hash: SHA-256 文件哈希。

        Returns:
            已存在的文档，或 None。
        """
        result = await db.execute(
            select(UploadedDocument).where(
                UploadedDocument.workspace_id == workspace_id,
                UploadedDocument.file_hash == file_hash,
                UploadedDocument.is_deleted.is_(False),
            ),
        )
        doc = result.scalar_one_or_none()
        return self._to_out(doc) if doc else None

    async def list_documents(
        self,
        db: AsyncSession,
        workspace_id: str,
        page: int = 1,
        page_size: int = 20,
        file_type: str | None = None,
        processing_status: str | None = None,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> tuple[list[DocumentOut], int]:
        """列出工作空间的文档。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            page: 页码。
            page_size: 每页条数。
            file_type: 文件类型筛选。
            processing_status: 处理状态筛选。
            sort_by: 排序字段。
            sort_desc: 是否倒序。

        Returns:
            (文档列表, 总数)。
        """
        base_filter = [
            UploadedDocument.workspace_id == workspace_id,
            UploadedDocument.is_deleted.is_(False),
        ]

        query = select(UploadedDocument).where(*base_filter)
        count_query = select(func.count(UploadedDocument.id)).where(*base_filter)

        if file_type:
            query = query.where(UploadedDocument.file_type == file_type)
            count_query = count_query.where(UploadedDocument.file_type == file_type)
        if processing_status:
            query = query.where(UploadedDocument.processing_status == processing_status)
            count_query = count_query.where(UploadedDocument.processing_status == processing_status)

        sort_field = sort_by if sort_by in self.ALLOWED_SORT_FIELDS else "created_at"
        sort_col = getattr(UploadedDocument, sort_field)
        query = query.order_by(sort_col.desc() if sort_desc else sort_col.asc())

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        docs = result.scalars().all()

        return [self._to_out(d) for d in docs], total

    async def update(
        self,
        db: AsyncSession,
        document_id: str,
        data: DocumentUpdate,
    ) -> DocumentOut | None:
        """更新文档。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。
            data: 更新数据。

        Returns:
            更新后的文档。
        """
        values: dict[str, Any] = {}
        for field in ("title", "description", "tags", "processing_status", "processing_error"):
            val = getattr(data, field, None)
            if val is not None:
                values[field] = val
        if not values:
            return await self.get(db, document_id)

        values["updated_at"] = datetime.now(UTC)
        await db.execute(
            update(UploadedDocument)
            .where(UploadedDocument.id == document_id)
            .values(**values),
        )
        await db.flush()
        return await self.get(db, document_id)

    async def soft_delete(
        self,
        db: AsyncSession,
        document_id: str,
    ) -> bool:
        """软删除文档。

        Args:
            db: 数据库会话。
            document_id: 文档 ID。

        Returns:
            是否删除成功。
        """
        result = await db.execute(
            update(UploadedDocument)
            .where(
                UploadedDocument.id == document_id,
                UploadedDocument.is_deleted.is_(False),
            )
            .values(is_deleted=True, deleted_at=datetime.now(UTC)),
        )
        await db.flush()
        return result.rowcount > 0

    async def get_stats(
        self,
        db: AsyncSession,
        workspace_id: str,
    ) -> DocumentStats:
        """获取文档统计信息。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。

        Returns:
            文档统计。
        """
        base_filter = [
            UploadedDocument.workspace_id == workspace_id,
            UploadedDocument.is_deleted.is_(False),
        ]

        # 总数
        total_result = await db.execute(
            select(func.count(UploadedDocument.id)).where(*base_filter),
        )
        total = total_result.scalar() or 0

        # 总大小
        size_result = await db.execute(
            select(func.coalesce(func.sum(UploadedDocument.file_size), 0)).where(*base_filter),
        )
        total_size = size_result.scalar() or 0

        # 按类型分布
        type_result = await db.execute(
            select(
                UploadedDocument.file_type,
                func.count(UploadedDocument.id),
            ).where(*base_filter).group_by(UploadedDocument.file_type),
        )
        by_type = dict(type_result.all())

        # 按状态分布
        status_result = await db.execute(
            select(
                UploadedDocument.processing_status,
                func.count(UploadedDocument.id),
            ).where(*base_filter).group_by(UploadedDocument.processing_status),
        )
        by_status = dict(status_result.all())

        return DocumentStats(
            total_documents=total,
            total_size_bytes=total_size,
            by_type=by_type,
            by_status=by_status,
        )

    @staticmethod
    def _to_out(doc: UploadedDocument | None) -> DocumentOut | None:
        """ORM 转 Pydantic。"""
        if doc is None:
            return None
        return DocumentOut(
            id=str(doc.id),
            workspace_id=str(doc.workspace_id),
            user_id=str(doc.user_id),
            original_filename=doc.original_filename,
            file_size=doc.file_size,
            file_type=doc.file_type,
            mime_type=doc.mime_type,
            file_hash=doc.file_hash,
            title=doc.title,
            description=doc.description,
            page_count=doc.page_count,
            word_count=doc.word_count,
            source_url=doc.source_url,
            processing_status=doc.processing_status,
            processing_error=doc.processing_error,
            indexed_at=doc.indexed_at.isoformat() if doc.indexed_at else None,
            entity_count=doc.entity_count,
            relation_count=doc.relation_count,
            tags=list(doc.tags) if doc.tags else [],
            is_deleted=doc.is_deleted,
            created_at=doc.created_at.isoformat() if doc.created_at else None,
            updated_at=doc.updated_at.isoformat() if doc.updated_at else None,
        )
