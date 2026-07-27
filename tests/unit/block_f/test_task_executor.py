"""任务执行器注册器单元测试。"""

from __future__ import annotations

import pytest

from contracts.models import Task, TaskType
from app.core.task_executor import (
    TaskExecutor,
    TaskExecutorRegistry,
    GenerateTaskExecutor,
    ReindexTaskExecutor,
)


class TestTaskExecutorRegistry:
    """任务执行器注册器单元测试。"""

    def setup_method(self) -> None:
        """每个测试前清理注册器。"""
        TaskExecutorRegistry._executors.clear()

    def test_register_and_get(self) -> None:
        """验证注册和获取执行器。"""
        executor = GenerateTaskExecutor()
        TaskExecutorRegistry.register(executor)
        retrieved = TaskExecutorRegistry.get(TaskType.GENERATE)
        assert retrieved is executor

    def test_get_unregistered_raises_error(self) -> None:
        """验证获取未注册的执行器抛出 ValueError。"""
        TaskExecutorRegistry._executors.clear()
        with pytest.raises(ValueError, match="未注册的任务执行器"):
            TaskExecutorRegistry.get(TaskType.EVALUATE)

    def test_register_multiple(self) -> None:
        """验证注册多个执行器。"""
        TaskExecutorRegistry._executors.clear()
        gen = GenerateTaskExecutor()
        reidx = ReindexTaskExecutor()
        TaskExecutorRegistry.register(gen)
        TaskExecutorRegistry.register(reidx)
        assert TaskExecutorRegistry.get(TaskType.GENERATE) is gen
        assert TaskExecutorRegistry.get(TaskType.REINDEX) is reidx


class TestGenerateTaskExecutor:
    """生成任务执行器单元测试。"""

    def test_task_type(self) -> None:
        """验证生成执行器的 task_type。"""
        executor = GenerateTaskExecutor()
        assert executor.task_type == TaskType.GENERATE

    def test_is_executor(self) -> None:
        """验证 GenerateTaskExecutor 是 TaskExecutor 的子类。"""
        executor = GenerateTaskExecutor()
        assert isinstance(executor, TaskExecutor)


class TestReindexTaskExecutor:
    """重索引任务执行器单元测试。"""

    def test_task_type(self) -> None:
        """验证重索引执行器的 task_type。"""
        executor = ReindexTaskExecutor()
        assert executor.task_type == TaskType.REINDEX

    def test_is_executor(self) -> None:
        """验证 ReindexTaskExecutor 是 TaskExecutor 的子类。"""
        executor = ReindexTaskExecutor()
        assert isinstance(executor, TaskExecutor)
