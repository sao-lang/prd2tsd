"""SaveSessionNode 落库回归测试 — 图执行后会话/消息真实持久化。"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.orchestrator.nodes.save_session import SaveSessionNode
from app.orchestrator.state import make_initial_state


class _FakeRepo:
    """记录 repository 调用的桩。"""

    def __init__(self) -> None:
        self.created: list[tuple] = []
        self.messages: list[tuple] = []
        self.updated: list[tuple] = []

    async def get_session(self, db, session_id: str):
        return None

    async def create_session(self, db, workspace_id: str, user_id: str, data, thread_id: str | None = None):
        class _Session:
            id = "sess-persist-1"

        self.created.append((workspace_id, user_id, thread_id))
        return _Session()

    async def add_message(self, db, session_id: str, user_id: str | None, data):
        self.messages.append((session_id, data.role, data.content))
        return None

    async def update_session(self, db, session_id: str, data):
        self.updated.append((session_id, data))
        return None


class _FakeService:
    def __init__(self) -> None:
        self.repository = _FakeRepo()


class _FakeDb:
    async def commit(self) -> None:
        return None


class _FakeConnector:
    def get_session(self):
        db = _FakeDb()

        @asynccontextmanager
        async def _cm():
            yield db

        return _cm()


@pytest.mark.asyncio
async def test_save_session_persists_messages_and_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """图结束时 SaveSessionNode 应创建会话并写入用户/AI 消息。"""
    import app.orchestrator.nodes.save_session as save_module

    fake_connector = _FakeConnector()
    monkeypatch.setattr(
        save_module.connection_manager,
        "get",
        lambda name: fake_connector,
    )

    node = SaveSessionNode(session_service=_FakeService())
    state = make_initial_state(
        task_id="task-1",
        prd_raw="请帮我写一个登录模块",
        workspace_id="ws-1",
        user_id="user-1",
    )
    state["status"] = "complete"
    state["chat_response"] = "这是生成的技术方案"
    state["intent"] = "complex_generation"

    result = await node.run(state)

    repo = node._session_service.repository
    assert result["status"] == "complete"
    assert repo.created, "应创建会话"
    assert repo.created[0][2] == "task-1", "thread_id 应绑定 task_id"
    assert ("sess-persist-1", "user", "请帮我写一个登录模块") in repo.messages
    assert ("sess-persist-1", "assistant", "这是生成的技术方案") in repo.messages
    assert repo.updated, "应更新会话状态/摘要"
