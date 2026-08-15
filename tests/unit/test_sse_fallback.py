"""SSE 事件总线回退回归测试 — runtime 未注入时事件仍应发出。"""

from __future__ import annotations

import asyncio

import pytest

from app.orchestrator.nodes.chat_node import ChatNode
from app.orchestrator.state import make_initial_state


class _FakeGateway:
    async def stream_complete(self, **kwargs):
        yield "你"
        yield "好"


@pytest.mark.asyncio
async def test_chat_node_publishes_without_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """chat_node 在 runtime=None 时应回退全局 EventBus 并发出 chat.status。"""
    from app.llm_gateway import gateway as real_gateway
    from app.streaming import event_bus

    monkeypatch.setattr("app.llm_gateway.gateway", _FakeGateway())
    state = make_initial_state(task_id="t-sse", prd_raw="你好")

    queue = await event_bus.subscribe("task:t-sse")
    try:
        await ChatNode().run(state)

        received: list[str] = []
        for _ in range(6):
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                received.append(event.type)
                if "chat.done" in received:
                    break
            except TimeoutError:
                break

        assert "chat.status" in received, f"应发出 chat.status，实际收到: {received}"
        assert "chat.done" in received
    finally:
        await event_bus.unsubscribe("task:t-sse", queue)
        monkeypatch.setattr("app.llm_gateway.gateway", real_gateway)
