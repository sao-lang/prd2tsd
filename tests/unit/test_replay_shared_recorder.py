"""决策回放共享实例回归测试 — 同一 recorder 首尾贯通。"""

from __future__ import annotations

import pytest

from app.observability.replay.recorder import DecisionRecorder, record_node_execution


@pytest.mark.asyncio
async def test_shared_recorder_trace_completes() -> None:
    """start_trace + record_decision + end_trace 在同一实例上应产出完整 trace。"""
    recorder = DecisionRecorder()
    await recorder.start_trace("task-replay")
    record = await record_node_execution(
        recorder,
        "task-replay",
        "analysis",
        {"input": "x"},
        "prompt",
        {"output": "y"},
    )
    trace = await recorder.end_trace("task-replay")

    assert record is not None
    assert trace is not None, "共享实例的 end_trace 应能找到 trace"
    assert trace.nodes, "trace 应包含至少一个节点记录"
