"""集成测试 — 统一交互入口三意图全流程（Block E B1）。

覆盖 对话（chat）/ 提问（knowledge_qa）/ 生成（complex_generation）
三条意图的同步分发链路：意图识别 → 路由分流 → 响应返回。

外部依赖（LangGraph orchestrator / TaskManager / LLM Gateway）以 mock 隔离，
聚焦「意图 → 分发 → 响应」的数据流完整性（对应 deep-review 数据流追踪要求）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes.interact import _classify_intent, _route_sync
from app.api.schemas.interact import InteractRequest
from app.models.user import User
from app.orchestrator.intent_classifier import IntentType


def _make_user() -> User:
    """构造测试用户（team_memberships 置空，避免触发懒加载）。"""
    user = User(
        id="user-1",
        email="tester@example.com",
        display_name="tester",
        hashed_password="x",
        auth_provider="jwt",
        auth_id="auth-1",
    )
    user.team_memberships = []
    return user


def _make_request(message: str, **kwargs: object) -> InteractRequest:
    """构造交互请求。"""
    return InteractRequest(message=message, **kwargs)


def _orchestrator_with(state: dict) -> MagicMock:
    """构造返回指定 final state 的 mock 编排器。"""
    orchestrator = MagicMock()
    orchestrator.ainvoke = AsyncMock(return_value=state)
    return orchestrator


class TestChatFlow:
    """对话意图全流程：识别 → 主编排图 → 文本响应。"""

    @pytest.mark.asyncio
    async def test_chat_roundtrip(self) -> None:
        """「你好」→ chat 意图 → 图执行 → 返回 chat_response。"""
        req = _make_request("你好")
        intent = await _classify_intent(req)
        assert intent.intent == IntentType.CHAT

        orchestrator = _orchestrator_with({
            "chat_response": "你好！我是 PRD2TSD 助手，可以帮你生成技术方案。",
            "status": "complete",
        })

        resp = await _route_sync(req, intent, _make_user(), orchestrator, MagicMock())

        assert resp.intent == "chat"
        assert resp.message == "你好！我是 PRD2TSD 助手，可以帮你生成技术方案。"

        # 关键数据流：意图被预写入初始 state，图内 classify 节点应幂等跳过分类
        initial_state = orchestrator.ainvoke.call_args.args[0]
        assert initial_state["intent"] == "chat"


class TestKnowledgeQaFlow:
    """提问意图全流程：识别 → 知识检索图执行 → 返回检索回答。"""

    @pytest.mark.asyncio
    async def test_knowledge_qa_roundtrip(self) -> None:
        """「知识图谱是什么」→ knowledge_qa 意图 → 图执行 → 返回检索回答。"""
        req = _make_request("知识图谱是什么")
        intent = await _classify_intent(req)
        assert intent.intent == IntentType.KNOWLEDGE_QA

        orchestrator = _orchestrator_with({
            "chat_response": "知识图谱是由实体与关系构成的语义网络。",
            "status": "complete",
        })

        resp = await _route_sync(req, intent, _make_user(), orchestrator, MagicMock())

        assert resp.intent == "knowledge_qa"
        assert resp.message == "知识图谱是由实体与关系构成的语义网络。"

    @pytest.mark.asyncio
    async def test_knowledge_qa_graph_exception_falls_back_to_llm(self) -> None:
        """图执行异常时降级为直接 LLM 回答（确保不返回空响应）。"""
        req = _make_request("知识图谱是什么")
        intent = await _classify_intent(req)

        orchestrator = MagicMock()
        orchestrator.ainvoke = AsyncMock(side_effect=RuntimeError("graph down"))

        with patch(
            "app.api.routes.interact.default_gateway",
            MagicMock(),
        ) as mock_gateway:
            mock_gateway.complete = AsyncMock(
                return_value=MagicMock(content="降级回答：知识图谱是语义网络。"),
            )
            resp = await _route_sync(req, intent, _make_user(), orchestrator, MagicMock())

        assert resp.intent == "chat"
        assert resp.message == "降级回答：知识图谱是语义网络。"
        mock_gateway.complete.assert_awaited_once()


class TestComplexGenerationFlow:
    """生成意图全流程：识别 → 创建异步任务 → 返回 task_id。"""

    @pytest.mark.asyncio
    async def test_complex_generation_roundtrip(self) -> None:
        """「生成一个用户服务的技术方案」→ complex_generation → 返回 task_id。"""
        req = _make_request("生成一个用户服务的技术方案")
        intent = await _classify_intent(req)
        assert intent.intent == IntentType.COMPLEX_GENERATION

        orchestrator = MagicMock()
        with patch(
            "app.task_manager.task_manager.create_task",
            new=AsyncMock(return_value="task-123"),
        ):
            resp = await _route_sync(req, intent, _make_user(), orchestrator, MagicMock())

        assert resp.intent == "complex_generation"
        assert resp.task_id == "task-123"
        assert "task-123" in resp.message
