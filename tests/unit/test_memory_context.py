"""记忆链路回归测试 — 历史消息注入与消费。"""

from __future__ import annotations

import pytest

from app.orchestrator.nodes.memory_context import build_memory_context, load_history_messages
from app.orchestrator.state import make_initial_state


@pytest.mark.asyncio
async def test_build_memory_context_uses_injected_history() -> None:
    """State 注入历史消息后，应产出记忆文本并写入 retrieved_memories。"""
    state = make_initial_state(
        task_id="t-mem",
        prd_raw="之前讨论的架构方案",
        history_messages=[
            {"role": "user", "content": "我们之前讨论过微服务架构"},
            {"role": "assistant", "content": "建议采用模块化单体"},
        ],
    )

    text = await build_memory_context(state)

    assert text, "应产出记忆上下文文本"
    assert state.get("retrieved_memories"), "应写入 retrieved_memories 供上层消费"
    assert state["retrieved_memories"][0]["content"]


@pytest.mark.asyncio
async def test_load_history_messages_returns_injected() -> None:
    """已注入的 _history_messages 应原样返回（不触发 DB）。"""
    state = make_initial_state(
        task_id="t-mem2",
        prd_raw="hi",
        history_messages=[{"role": "user", "content": "hello"}],
    )
    messages = await load_history_messages(state)
    assert messages == [{"role": "user", "content": "hello"}]
