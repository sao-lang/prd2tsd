"""会话历史数据库访问层 — Session + SessionMessage CRUD。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block_e import Session, SessionMessage
from app.session_history.models import (
    MessageCreate,
    PageResult,
    SessionCreate,
    SessionMessageOut,
    SessionOut,
    SessionUpdate,
)


class SessionRepository:
    """会话 + 消息的数据库访问层。"""

    async def create_session(
        self,
        db: AsyncSession,
        workspace_id: str,
        user_id: str,
        data: SessionCreate,
    ) -> SessionOut:
        """创建新会话。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            user_id: 用户 ID。
            data: 创建参数。

        Returns:
            创建的会话信息。
        """
        session = Session(
            workspace_id=workspace_id,
            user_id=user_id,
            title=data.title,
            session_type=data.session_type or "generate",
            tags=data.tags or [],
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return self._to_session_out(session)

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> SessionOut | None:
        """获取单个会话。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。

        Returns:
            会话信息，不存在时返回 None。
        """
        result = await db.execute(
            select(Session).where(Session.id == session_id, Session.deleted_at.is_(None)),
        )
        session = result.scalar_one_or_none()
        return self._to_session_out(session) if session else None

    async def list_sessions(
        self,
        db: AsyncSession,
        workspace_id: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        session_type: str | None = None,
        sort_by: str = "last_message_at",
        sort_desc: bool = True,
    ) -> PageResult:
        """列出工作空间的会话（分页）。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            page: 页码，从 1 开始。
            page_size: 每页条数。
            status: 按状态筛选。
            session_type: 按类型筛选。
            sort_by: 排序字段。
            sort_desc: 是否倒序。

        Returns:
            分页结果。
        """
        query = select(Session).where(
            Session.workspace_id == workspace_id,
            Session.deleted_at.is_(None),
        )
        count_query = select(func.count(Session.id)).where(
            Session.workspace_id == workspace_id,
            Session.deleted_at.is_(None),
        )

        if status:
            query = query.where(Session.status == status)
            count_query = count_query.where(Session.status == status)
        if session_type:
            query = query.where(Session.session_type == session_type)
            count_query = count_query.where(Session.session_type == session_type)

        # 排序
        sort_col = getattr(Session, sort_by, Session.last_message_at)
        query = query.order_by(sort_col.desc() if sort_desc else sort_col.asc())

        # 总数
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        sessions = result.scalars().all()

        return PageResult(
            items=[self._to_session_out(s) for s in sessions],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    async def update_session(
        self,
        db: AsyncSession,
        session_id: str,
        data: SessionUpdate,
    ) -> SessionOut | None:
        """更新会话。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。
            data: 更新参数。

        Returns:
            更新后的会话信息。
        """
        values: dict[str, Any] = {}
        for field in ("title", "session_type", "status", "summary", "tags", "rating"):
            val = getattr(data, field, None)
            if val is not None:
                values[field] = val
        if not values:
            return await self.get_session(db, session_id)

        values["updated_at"] = datetime.now(UTC)
        await db.execute(
            update(Session).where(Session.id == session_id).values(**values),
        )
        await db.flush()
        return await self.get_session(db, session_id)

    async def soft_delete_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> bool:
        """软删除会话。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。

        Returns:
            是否删除成功。
        """
        result = await db.execute(
            update(Session)
            .where(Session.id == session_id, Session.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC), status="deleted"),
        )
        await db.flush()
        return result.rowcount > 0

    async def add_message(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str | None,
        data: MessageCreate,
    ) -> SessionMessageOut:
        """添加消息到会话。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。
            user_id: 用户 ID。
            data: 消息内容。

        Returns:
            创建的消息信息。
        """
        # 计算 turn_index
        result = await db.execute(
            select(func.coalesce(func.max(SessionMessage.turn_index), -1))
            .where(SessionMessage.session_id == session_id),
        )
        max_turn = result.scalar() or -1

        message = SessionMessage(
            session_id=session_id,
            user_id=user_id,
            role=data.role,
            content=data.content,
            content_type=data.content_type,
            attachments=data.attachments or [],
            parent_message_id=data.parent_message_id,
            turn_index=max_turn + 1,
        )
        db.add(message)

        # 更新会话统计
        await db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                message_count=Session.message_count + 1,
                last_message_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        )
        await db.flush()
        await db.refresh(message)
        return self._to_message_out(message)

    async def get_messages(
        self,
        db: AsyncSession,
        session_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> PageResult:
        """获取会话的消息列表。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。
            page: 页码。
            page_size: 每页条数。

        Returns:
            分页消息列表。
        """
        query = (
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .order_by(SessionMessage.turn_index.asc())
        )
        count_query = (
            select(func.count(SessionMessage.id))
            .where(SessionMessage.session_id == session_id)
        )

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await db.execute(query)
        messages = result.scalars().all()

        return PageResult(
            items=[self._to_message_out(m) for m in messages],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, (total + page_size - 1) // page_size),
        )

    async def cleanup_expired(
        self,
        db: AsyncSession,
        workspace_id: str,
        before: datetime,
    ) -> int:
        """清理指定时间之前的过期会话。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            before: 过期时间点。

        Returns:
            清理的会话数。
        """
        result = await db.execute(
            update(Session)
            .where(
                Session.workspace_id == workspace_id,
                Session.deleted_at.is_(None),
                Session.last_message_at < before,
            )
            .values(deleted_at=datetime.now(UTC), status="deleted"),
        )
        await db.flush()
        return result.rowcount or 0

    async def get_expired_sessions(
        self,
        db: AsyncSession,
        workspace_id: str,
        before: datetime,
    ) -> list[Session]:
        """获取过期会话列表。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            before: 过期时间点。

        Returns:
            过期会话列表。
        """
        result = await db.execute(
            select(Session).where(
                Session.workspace_id == workspace_id,
                Session.deleted_at.is_(None),
                Session.last_message_at < before,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _to_session_out(session: Session) -> SessionOut:
        """ORM 转 Pydantic 响应。"""
        return SessionOut(
            id=str(session.id),
            workspace_id=str(session.workspace_id),
            user_id=str(session.user_id),
            title=session.title,
            session_type=session.session_type,
            status=session.status,
            summary=session.summary,
            message_count=session.message_count,
            token_count=session.token_count,
            cost_usd=float(session.cost_usd) if session.cost_usd else 0.0,
            rating=session.rating,
            tags=list(session.tags) if session.tags else [],
            created_at=session.created_at.isoformat() if session.created_at else None,
            updated_at=session.updated_at.isoformat() if session.updated_at else None,
            last_message_at=session.last_message_at.isoformat() if session.last_message_at else None,
        )

    @staticmethod
    def _to_message_out(msg: SessionMessage) -> SessionMessageOut:
        """ORM 转 Pydantic 响应。"""
        return SessionMessageOut(
            id=str(msg.id),
            session_id=str(msg.session_id),
            role=msg.role,
            content=msg.content,
            content_type=msg.content_type,
            attachments=list(msg.attachments) if msg.attachments else [],
            turn_index=msg.turn_index,
            token_count=msg.token_count,
            cost_usd=float(msg.cost_usd) if msg.cost_usd else 0.0,
            latency_ms=msg.latency_ms,
            model_used=msg.model_used,
            created_at=msg.created_at.isoformat() if msg.created_at else None,
        )
