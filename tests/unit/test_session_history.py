"""会话历史模块单元测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.session_history.cleanup import SessionCleanupPolicy
from app.session_history.exporter import SessionExporter
from app.session_history.models import MessageCreate, SessionCreate, SessionUpdate
from app.session_history.repository import SessionRepository
from app.session_history.search import SessionSearchService
from app.session_history.service import SessionHistoryService
from app.session_history.summarizer import SessionSummarizer


class TestSessionRepository:
    """会话仓库单元测试。"""

    @pytest.mark.asyncio
    async def test_to_session_out_converts_orm(self, db_session: AsyncSession) -> None:
        """验证 ORM 转 Pydantic 响应。"""
        from app.models.block_e import Session

        session = Session(
            workspace_id="ws-test",
            user_id="user-test",
            title="测试会话",
        )
        db_session.add(session)
        await db_session.flush()

        repo = SessionRepository()
        result = await repo.get_session(db_session, str(session.id))
        assert result is not None
        assert result.title == "测试会话"
        assert result.workspace_id == "ws-test"

    @pytest.mark.asyncio
    async def test_create_and_list_sessions(self, db_session: AsyncSession) -> None:
        """验证创建会话 → 列表可见。"""
        repo = SessionRepository()
        data = SessionCreate(title="列表测试", session_type="generate")
        created = await repo.create_session(db_session, "ws-list", "user-list", data)
        assert created.id is not None

        result = await repo.list_sessions(db_session, "ws-list")
        assert result.total >= 1
        assert any(s.title == "列表测试" for s in result.items)

    @pytest.mark.asyncio
    async def test_soft_delete(self, db_session: AsyncSession) -> None:
        """验证软删除。"""
        repo = SessionRepository()
        data = SessionCreate(title="待删除会话")
        created = await repo.create_session(db_session, "ws-del", "user-del", data)

        deleted = await repo.soft_delete_session(db_session, created.id)
        assert deleted is True

        fetched = await repo.get_session(db_session, created.id)
        assert fetched is None  # 软删除后不可见

    @pytest.mark.asyncio
    async def test_add_and_get_messages(self, db_session: AsyncSession) -> None:
        """验证添加消息 → 可获取。"""
        repo = SessionRepository()
        session = await repo.create_session(
            db_session, "ws-msg", "user-msg",
            SessionCreate(title="消息测试"),
        )

        msg = await repo.add_message(
            db_session, session.id, "user-msg",
            MessageCreate(role="user", content="订单服务用什么数据库？"),
        )
        assert msg.turn_index == 0

        result = await repo.get_messages(db_session, session.id)
        assert result.total == 1
        assert result.items[0].content == "订单服务用什么数据库？"

    @pytest.mark.asyncio
    async def test_update_session(self, db_session: AsyncSession) -> None:
        """验证更新会话。"""
        repo = SessionRepository()
        session = await repo.create_session(
            db_session, "ws-upd", "user-upd",
            SessionCreate(title="原标题"),
        )
        updated = await repo.update_session(
            db_session, session.id, SessionUpdate(title="新标题", rating=4),
        )
        assert updated is not None
        assert updated.title == "新标题"
        assert updated.rating == 4


class TestSessionSearch:
    """会话搜索单元测试。"""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, db_session: AsyncSession) -> None:
        """验证空查询返回空列表。"""
        searcher = SessionSearchService()
        results = await searcher.search_messages(db_session, "ws", "")
        assert len(results) == 0

        results = await searcher.search_sessions(db_session, "ws", "")
        assert len(results) == 0


class TestSessionExporter:
    """会话导出单元测试。"""

    def test_markdown_export_format(self) -> None:
        """验证 Markdown 导出格式。"""
        from app.models.block_e import Session, SessionMessage

        session = Session(
            id="test-id",
            workspace_id="ws",
            user_id="user",
            title="测试会话标题",
            message_count=2,
        )
        msgs = [
            SessionMessage(
                id="m1", session_id="test-id",
                role="user", content="你好", turn_index=0,
            ),
            SessionMessage(
                id="m2", session_id="test-id",
                role="assistant", content="你好！有什么可以帮你的？", turn_index=1,
            ),
        ]
        exporter = SessionExporter()
        md = exporter._to_markdown(session, msgs)
        assert "# 测试会话标题" in md
        assert "👤 **用户**" in md
        assert "🤖 **助手**" in md
        assert "你好" in md

    def test_json_export_format(self) -> None:
        """验证 JSON 导出格式。"""
        from app.models.block_e import Session, SessionMessage

        session = Session(
            id="test-id", workspace_id="ws", user_id="user",
            title="测试会话", message_count=1,
        )
        msgs = [
            SessionMessage(
                id="m1", session_id="test-id",
                role="user", content="测试", turn_index=0,
            ),
        ]
        exporter = SessionExporter()
        json_str = exporter._to_json(session, msgs)
        assert '"title": "测试会话"' in json_str
        assert '"role": "user"' in json_str


class TestSessionSummarizer:
    """摘要生成器单元测试。"""

    @pytest.mark.asyncio
    async def test_generate_title_from_message(self) -> None:
        """验证从首条消息生成标题。"""
        summarizer = SessionSummarizer()
        title = await summarizer.generate_title("请问订单系统如何设计？")
        assert len(title) > 0
        assert "订单" in title

    @pytest.mark.asyncio
    async def test_generate_title_empty(self) -> None:
        """验证空消息返回默认标题。"""
        summarizer = SessionSummarizer()
        title = await summarizer.generate_title("")
        assert title == "新会话"


class TestCleanupPolicy:
    """老化清理策略单元测试。"""

    def test_retention_days_free(self) -> None:
        """验证 Free 套餐保留 30 天。"""
        policy = SessionCleanupPolicy()
        assert policy.get_retention_days("free") == 30

    def test_retention_days_pro(self) -> None:
        """验证 Pro 套餐保留 180 天。"""
        policy = SessionCleanupPolicy()
        assert policy.get_retention_days("pro") == 180

    def test_retention_days_enterprise(self) -> None:
        """验证 Enterprise 套餐不限。"""
        policy = SessionCleanupPolicy()
        assert policy.get_retention_days("enterprise") == 0


class TestSessionService:
    """会话历史服务单元测试。"""

    @pytest.mark.asyncio
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        """验证服务层创建并获取会话。"""
        svc = SessionHistoryService()
        created = await svc.create_session(
            db_session, "ws-svc", "user-svc",
            SessionCreate(title="服务测试"),
        )
        assert created.title == "服务测试"

        fetched = await svc.get_session(db_session, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_auto_title(self) -> None:
        """验证自动标题生成。"""
        svc = SessionHistoryService()
        title = await svc.auto_title("如何实现微服务架构？")
        assert len(title) > 0
