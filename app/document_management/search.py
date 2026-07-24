"""文档搜索 — PostgreSQL FTS + 语义向量混合搜索。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_management.models import SearchResult
from app.models.block_e import UploadedDocument


class DocumentSearchService:
    """文档搜索服务。

    双路搜索：
    1. FTS：PostgreSQL `to_tsvector` 全文搜索文件名 + 描述
    2. 语义：向量相似度搜索（占位，块 B PGVector 集成）
    """

    async def search(
        self,
        db: AsyncSession,
        workspace_id: str,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SearchResult]:
        """搜索文档（FTS + 语义融合）。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            query: 搜索关键词。
            page: 页码。
            page_size: 每页条数。

        Returns:
            搜索结果列表。
        """
        if not query.strip():
            return await self._list_recent(db, workspace_id, page_size)

        results = await self._fts_search(db, workspace_id, query, page, page_size)
        return results

    async def _fts_search(
        self,
        db: AsyncSession,
        workspace_id: str,
        query: str,
        page: int,
        page_size: int,
    ) -> list[SearchResult]:
        """PostgreSQL FTS 全文搜索。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            query: 搜索关键词。
            page: 页码。
            page_size: 每页条数。

        Returns:
            搜索结果。
        """
        ts_query = func.plainto_tsquery("simple", query)
        ts_vector = func.to_tsvector(
            "simple",
            func.coalesce(UploadedDocument.title, "")
            + " "
            + func.coalesce(UploadedDocument.description, "")
            + " "
            + UploadedDocument.original_filename,
        )
        ts_rank = func.ts_rank(ts_vector, ts_query)

        stmt = (
            select(UploadedDocument, ts_rank.label("score"))
            .where(
                UploadedDocument.workspace_id == workspace_id,
                UploadedDocument.is_deleted.is_(False),
                ts_vector.op("@@")(ts_query),
            )
            .order_by(ts_rank.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        rows = result.all()

        search_results: list[SearchResult] = []
        for row in rows:
            doc = row[0] if hasattr(row, "__getitem__") else row.UploadedDocument
            score_val = row.score if hasattr(row, "score") else getattr(row, "score", 0.0)
            search_results.append(SearchResult(
                document_id=str(doc.id),
                title=doc.title or doc.original_filename,
                description=doc.description,
                file_type=doc.file_type,
                file_size=doc.file_size,
                score=float(score_val) if score_val else 0.0,
                match_type="fts",
                created_at=doc.created_at.isoformat() if doc.created_at else None,
            ))
        return search_results

    async def _list_recent(
        self,
        db: AsyncSession,
        workspace_id: str,
        limit: int = 20,
    ) -> list[SearchResult]:
        """列出最近文档（无搜索词时）。"""
        stmt = (
            select(UploadedDocument)
            .where(
                UploadedDocument.workspace_id == workspace_id,
                UploadedDocument.is_deleted.is_(False),
            )
            .order_by(UploadedDocument.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        docs = result.scalars().all()

        return [
            SearchResult(
                document_id=str(d.id),
                title=d.title or d.original_filename,
                description=d.description,
                file_type=d.file_type,
                file_size=d.file_size,
                score=1.0,
                match_type="fts",
                created_at=d.created_at.isoformat() if d.created_at else None,
            )
            for d in docs
        ]
