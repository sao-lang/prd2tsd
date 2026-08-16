"""Runtime 线程级注册表回归测试（2026-08-16 条目 31）。

验证 Runtime 注入不写入 State（避免不可序列化对象进入 checkpoint），
且按 thread_id 注册/读取/注销的完整生命周期。
"""

from __future__ import annotations

import pytest

from app.orchestrator.runtime import (
    RuntimeInjector,
    get_registered_runtime,
    register_runtime,
    unregister_runtime,
)
from app.orchestrator.state import OrchestratorRuntime


def test_register_get_unregister() -> None:
    """注册 → 读取 → 注销全流程。"""
    runtime = OrchestratorRuntime(current_user_id="u1")
    register_runtime("t1", runtime)
    assert get_registered_runtime("t1") is runtime
    unregister_runtime("t1")
    assert get_registered_runtime("t1") is None


@pytest.mark.asyncio
async def test_inject_registers_runtime_without_mutating_state() -> None:
    """inject 只写注册表，不向 State 写入 _runtime。"""
    injector = RuntimeInjector()
    state: dict = {"task_id": "t1", "user_id": "u1", "workspace_id": "w1"}
    result = await injector.inject(state)

    runtime = get_registered_runtime("t1")
    assert runtime is not None
    assert runtime.current_user_id == "u1"
    assert runtime.current_workspace_id == "w1"
    assert "_runtime" not in result
    assert result == state
    unregister_runtime("t1")
