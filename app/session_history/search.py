"""会话全文搜索 — PostgreSQL FTS 搜索消息内容。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block_e import Session, SessionMessage
from app.session_history.models import SessionSearchResult


class SessionSearchService:
    """会话全文搜索服务。

    使用 PostgreSQL 内置 `to_tsvector` / `plainto_tsquery` 做全文搜索。
    """

    async def search_messages(
        self,
        db: AsyncSession,
        workspace_id: str,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SessionSearchResult]:
        """全文搜索消息内容。

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
            return []

        ts_query = func.plainto_tsquery("simple", query)
        ts_vector = func.to_tsvector("simple", SessionMessage.content)
        ts_rank = func.ts_rank(ts_vector, ts_query)

        stmt = (
            select(
                SessionMessage.id,
                SessionMessage.session_id,
                Session.title,
                SessionMessage.content,
                SessionMessage.role,
                SessionMessage.turn_index,
                ts_rank.label("score"),
                SessionMessage.created_at,
            )
            .join(Session, SessionMessage.session_id == Session.id)
            .where(
                Session.workspace_id == workspace_id,
                Session.deleted_at.is_(None),
                ts_vector.op("@@")(ts_query),
            )
            .order_by(ts_rank.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await db.execute(stmt)
        rows = result.all()

        return [
            SessionSearchResult(
                session_id=str(row.session_id),
                message_id=str(row.id),
                session_title=row.title,
                content=row.content[:300],
                role=row.role,
                turn_index=row.turn_index,
                score=float(row.score) if row.score else 0.0,
                created_at=row.created_at.isoformat() if row.created_at else None,
            )
            for row in rows
        ]

    async def search_sessions(
        self,
        db: AsyncSession,
        workspace_id: str,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SessionSearchResult]:
        """按会话标题搜索。

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
            return []

        like_pattern = f"%{query}%"
        stmt = (
            select(Session)
            .where(
                Session.workspace_id == workspace_id,
                Session.deleted_at.is_(None),
                Session.title.ilike(like_pattern),
            )
            .order_by(Session.last_message_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        sessions = result.scalars().all()

        return [
            SessionSearchResult(
                session_id=str(s.id),
                message_id="",
                session_title=s.title,
                content=s.summary or s.title,
                role="assistant",
                turn_index=0,
                score=1.0,
                created_at=s.created_at.isoformat() if s.created_at else None,
            )
            for s in sessions
        ]
