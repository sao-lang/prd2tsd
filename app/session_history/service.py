"""会话历史服务 — 会话 CRUD + 消息管理 + 搜索 + 导出。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.session_history.cleanup import SessionCleanupPolicy
from app.session_history.exporter import SessionExporter
from app.session_history.models import (
    MessageCreate,
    PageResult,
    SessionCreate,
    SessionMessageOut,
    SessionOut,
    SessionSearchResult,
    SessionUpdate,
)
from app.session_history.repository import SessionRepository
from app.session_history.search import SessionSearchService
from app.session_history.summarizer import SessionSummarizer

logger = get_logger("prd2tsd.session_service")


class SessionHistoryService:
    """会话历史服务 — 统一对外接口。

    组合 Repository / Search / Export / Summarizer / Cleanup 等功能。
    """

    def __init__(
        self,
        repository: SessionRepository | None = None,
        search_service: SessionSearchService | None = None,
        exporter: SessionExporter | None = None,
        summarizer: SessionSummarizer | None = None,
        cleanup_policy: SessionCleanupPolicy | None = None,
    ) -> None:
        """初始化会话历史服务。

        Args:
            repository: 会话仓库。
            search_service: 搜索服务。
            exporter: 导出服务。
            summarizer: 摘要生成器。
            cleanup_policy: 老化清理策略。
        """
        self.repository = repository or SessionRepository()
        self.search_service = search_service or SessionSearchService()
        self.exporter = exporter or SessionExporter()
        self.summarizer = summarizer or SessionSummarizer()
        self.cleanup_policy = cleanup_policy or SessionCleanupPolicy(self.repository)

    async def create_session(
        self,
        db: AsyncSession,
        workspace_id: str,
        user_id: str,
        data: SessionCreate,
    ) -> SessionOut:
        """创建会话。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            user_id: 用户 ID。
            data: 创建参数。

        Returns:
            创建的会话。
        """
        return await self.repository.create_session(db, workspace_id, user_id, data)

    async def get_session(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> SessionOut | None:
        """获取会话。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。

        Returns:
            会话信息。
        """
        return await self.repository.get_session(db, session_id)

    async def list_sessions(
        self,
        db: AsyncSession,
        workspace_id: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        session_type: str | None = None,
        sort_by: str = "last_message_at",
    ) -> PageResult:
        """列出工作空间的会话。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            page: 页码。
            page_size: 每页条数。
            status: 筛选状态。
            session_type: 筛选类型。
            sort_by: 排序字段。

        Returns:
            分页结果。
        """
        return await self.repository.list_sessions(
            db, workspace_id, page, page_size, status, session_type, sort_by,
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
            更新后的会话。
        """
        return await self.repository.update_session(db, session_id, data)

    async def delete_session(
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
        return await self.repository.soft_delete_session(db, session_id)

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
            创建的消息。
        """
        return await self.repository.add_message(db, session_id, user_id, data)

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
        return await self.repository.get_messages(db, session_id, page, page_size)

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
            搜索结果。
        """
        return await self.search_service.search_messages(
            db, workspace_id, query, page, page_size,
        )

    async def search_sessions(
        self,
        db: AsyncSession,
        workspace_id: str,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SessionSearchResult]:
        """按标题搜索会话。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            query: 搜索关键词。
            page: 页码。
            page_size: 每页条数。

        Returns:
            搜索结果。
        """
        return await self.search_service.search_sessions(
            db, workspace_id, query, page, page_size,
        )

    async def export_session(
        self,
        db: AsyncSession,
        session_id: str,
        fmt: str = "markdown",
    ) -> str:
        """导出会话。

        Args:
            db: 数据库会话。
            session_id: 会话 ID。
            fmt: 格式（markdown/json）。

        Returns:
            导出内容。
        """
        return await self.exporter.export(db, session_id, fmt)

    async def auto_title(
        self,
        first_message: str,
    ) -> str:
        """自动生成会话标题。

        Args:
            first_message: 首条消息。

        Returns:
            生成的标题。
        """
        return await self.summarizer.generate_title(first_message)

    async def cleanup_expired(
        self,
        db: AsyncSession,
        workspace_id: str,
        plan: str = "free",
    ) -> int:
        """执行老化清理。

        Args:
            db: 数据库会话。
            workspace_id: 工作空间 ID。
            plan: 套餐类型。

        Returns:
            清理的会话数。
        """
        return await self.cleanup_policy.cleanup(db, workspace_id, plan)


# 全局单例
session_service = SessionHistoryService()
