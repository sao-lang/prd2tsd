"""TaskManager 任务指标单元测试（WP1-C：TASKS_TOTAL / TASKS_DURATION）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.observability.metrics import TASKS_TOTAL
from app.task_manager import TaskManager


def _count(status: str) -> float:
    """读取指定 status 的任务计数。

    Args:
        status: 任务状态（created/completed/failed）。

    Returns:
        当前计数。
    """
    return TASKS_TOTAL.labels(status=status)._value.get()


def _make_record(orchestrator: MagicMock) -> dict:
    """构造任务记录。

    Args:
        orchestrator: mock 编排器。

    Returns:
        任务记录 dict。
    """
    return {
        "task_id": "t1",
        "thread_id": "th1",
        "orchestrator": orchestrator,
        "status": "running",
        "progress": 0.0,
        "stage": "",
        "interrupt_stage": "",
        "result": None,
        "evaluation": None,
        "error": None,
        "created_at": "",
        "updated_at": "",
    }


async def test_create_task_increments_created() -> None:
    """验证 create_task 记录 created 指标。"""
    before = _count("created")
    mgr = TaskManager()
    with patch.object(mgr, "_execute_task", AsyncMock()):
        await mgr.create_task(prd_raw="PRD", orchestrator=MagicMock())
    assert _count("created") == before + 1


async def test_execute_task_completed_metrics() -> None:
    """验证任务成功完成记录 completed + duration。"""
    before = _count("completed")
    mgr = TaskManager()
    orchestrator = MagicMock()

    async def fake_astream(state: dict, config: dict) -> object:
        """模拟图执行返回完成状态。"""
        yield {"status": "complete", "progress": 1.0, "generation_result": "ok"}

    orchestrator.astream = fake_astream
    record = _make_record(orchestrator)
    with patch.object(mgr, "_tasks", {"t1": record}):
        await mgr._execute_task("t1", "PRD", "md", "", "", "", [])

    assert _count("completed") == before + 1


async def test_execute_task_failed_metrics() -> None:
    """验证任务失败记录 failed 指标。"""
    before = _count("failed")
    mgr = TaskManager()
    orchestrator = MagicMock()

    async def failing_astream(state: dict, config: dict) -> object:
        """模拟图执行抛异常（async generator）。"""
        raise RuntimeError("boom")
        yield  # pragma: no cover — 使函数成为 async generator

    orchestrator.astream = failing_astream
    record = _make_record(orchestrator)
    with patch.object(mgr, "_tasks", {"t1": record}):
        await mgr._execute_task("t1", "PRD", "md", "", "", "", [])

    assert _count("failed") == before + 1


async def test_execute_task_paused_not_counted_as_completed() -> None:
    """验证 interrupt 暂停（paused）不计入 completed。"""
    before = _count("completed")
    mgr = TaskManager()
    orchestrator = MagicMock()

    async def pause_astream(state: dict, config: dict) -> object:
        """模拟图执行后停在 running（interrupt）。"""
        yield {"status": "running", "current_stage": "planning"}

    orchestrator.astream = pause_astream
    record = _make_record(orchestrator)
    with patch.object(mgr, "_tasks", {"t1": record}):
        await mgr._execute_task("t1", "PRD", "md", "", "", "", [])

    assert _count("completed") == before
    assert record["status"] == "paused"
