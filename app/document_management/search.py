"""文档搜索 — PostgreSQL FTS + 语义向量混合搜索。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.document_management.models import SearchResult
from app.models.block_e import UploadedDocument

logger = get_logger("prd2tsd.document_search")


class DocumentSearchService:
    """文档搜索服务。

    双路搜索：
    1. FTS：PostgreSQL `to_tsvector` 全文搜索文件名 + 描述
    2. 语义：查询向量 → text_unit_embeddings 相似度 → 聚合到文档（2026-08-16 实现）
    """

    def __init__(self, vector_store: Any | None = None) -> None:
        """初始化文档搜索服务。

        Args:
            vector_store: PGVectorStore 实例（可选，测试注入）。
        """
        self._vector_store = vector_store

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

        fts_results = await self._fts_search(db, workspace_id, query, page, page_size)
        semantic_results: list[SearchResult] = []
        try:
            semantic_results = await self._semantic_search(db, workspace_id, query, page_size)
        except Exception as exc:
            logger.warning("语义检索失败（降级仅 FTS）: %s", exc)
        return self._merge_results(fts_results, semantic_results, page_size)

    async def _semantic_search(
        self,
        db: AsyncSession,
        workspace_id: str,
        query: str,
        limit: int = 20,
    ) -> list[SearchResult]:
        """语义检索 — 查询向量 → text_unit_embeddings 相似度 → 聚合到文档。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            query: 搜索关键词。
            limit: 返回条数上限。

        Returns:
            语义命中的文档列表（按最高块相似度排序）。
        """
        from app.knowledge_layer.vector_store import PGVectorStore
        from app.llm_gateway import gateway

        resp = await gateway.embed(texts=[query], task_type="embedding")
        if not resp.embeddings or not resp.embeddings[0]:
            return []

        vector_store = self._vector_store or PGVectorStore(session=db)
        docs = await vector_store.similarity_search(
            embedding=resp.embeddings[0],
            table="text_unit_embeddings",
            top_k=limit,
            workspace_id=workspace_id,
        )

        # 同一文档的多个 chunk 取最高相似度
        best: dict[str, float] = {}
        for doc in docs:
            doc_id = doc.metadata.get("document_id", "")
            if doc_id:
                best[doc_id] = max(best.get(doc_id, 0.0), doc.score)

        if not best:
            return []

        result = await db.execute(
            select(UploadedDocument).where(UploadedDocument.id.in_(list(best))),
        )
        doc_map = {str(d.id): d for d in result.scalars().all()}

        items: list[SearchResult] = []
        for doc_id, score in sorted(best.items(), key=lambda kv: kv[1], reverse=True):
            d = doc_map.get(doc_id)
            if d is None:
                continue
            items.append(
                SearchResult(
                    document_id=doc_id,
                    title=d.title or d.original_filename,
                    description=d.description,
                    file_type=d.file_type,
                    file_size=d.file_size,
                    score=round(score, 4),
                    match_type="semantic",
                    created_at=d.created_at.isoformat() if d.created_at else None,
                ),
            )
        return items

    @staticmethod
    def _merge_results(
        fts: list[SearchResult],
        semantic: list[SearchResult],
        limit: int = 20,
    ) -> list[SearchResult]:
        """合并 FTS 与语义结果：按 document_id 去重，保留更高分。

        Args:
            fts: FTS 搜索结果。
            semantic: 语义搜索结果。
            limit: 返回条数上限。

        Returns:
            去重排序后的结果列表。
        """
        merged: dict[str, SearchResult] = {}
        for item in [*fts, *semantic]:
            existing = merged.get(item.document_id)
            if existing is None or item.score > existing.score:
                merged[item.document_id] = item
        return sorted(merged.values(), key=lambda r: r.score, reverse=True)[:limit]

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
