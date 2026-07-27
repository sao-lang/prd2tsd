"""任务队列单元测试。"""

from __future__ import annotations

import pytest

from contracts.models import Task, TaskStatus, TaskType
from app.core.task_queue import TaskQueue


class TestTaskQueue:
    """任务队列单元测试。"""

    @pytest.fixture
    def queue(self) -> TaskQueue:
        return TaskQueue()

    @pytest.fixture
    def task_low(self) -> Task:
        return Task(
            id="low-1",
            type=TaskType.EVALUATE,
            priority=5,
            workspace_id="ws-1",
            user_id="user-1",
        )

    @pytest.fixture
    def task_high(self) -> Task:
        return Task(
            id="high-1",
            type=TaskType.GENERATE,
            priority=0,
            workspace_id="ws-1",
            user_id="user-1",
        )

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, queue: TaskQueue) -> None:
        """验证入队和出队。"""
        task = Task(
            id="test-1",
            type=TaskType.GENERATE,
            priority=0,
            workspace_id="ws-1",
        )
        await queue.enqueue(task)
        result = await queue.dequeue()
        assert result is not None
        assert result.id == "test-1"

    @pytest.mark.asyncio
    async def test_priority_order(self, queue: TaskQueue, task_high: Task, task_low: Task) -> None:
        """验证高优先级任务先出队。"""
        await queue.enqueue(task_low)   # priority=5
        await queue.enqueue(task_high)  # priority=0
        first = await queue.dequeue()
        assert first is not None
        assert first.id == "high-1"
        second = await queue.dequeue()
        assert second is not None
        assert second.id == "low-1"

    @pytest.mark.asyncio
    async def test_dequeue_empty(self, queue: TaskQueue) -> None:
        """验证空队列出队返回 None。"""
        result = await queue.dequeue()
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_queued_task(self, queue: TaskQueue) -> None:
        """验证取消队列中的任务。"""
        task = Task(id="cancel-me", type=TaskType.GENERATE, priority=0)
        await queue.enqueue(task)
        cancelled = await queue.cancel("cancel-me")
        assert cancelled is True
        # 出队不应再返回该任务
        result = await queue.dequeue()
        assert result is None or result.id != "cancel-me"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, queue: TaskQueue) -> None:
        """验证取消不存在的任务返回 False。"""
        cancelled = await queue.cancel("not-exist")
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_get_status_from_queue(self, queue: TaskQueue) -> None:
        """验证从队列中查询任务状态。"""
        task = Task(id="status-test", type=TaskType.GENERATE, priority=0)
        await queue.enqueue(task)
        status = await queue.get_status("status-test")
        assert status is not None
        assert status.id == "status-test"
        assert status.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_status_nonexistent(self, queue: TaskQueue) -> None:
        """验证查询不存在的任务返回 None。"""
        status = await queue.get_status("not-exist")
        assert status is None
