"""批量任务单元测试。"""

from __future__ import annotations

import pytest

from app.batch.scheduler import BatchScheduler
from app.batch.tasks import BatchTaskService


class TestBatchTaskService:
    """批量任务服务单元测试。"""

    @pytest.mark.asyncio
    async def test_reindex_documents(self) -> None:
        """验证批量重索引。"""
        svc = BatchTaskService()
        task_id = await svc.reindex_documents("ws-1", ["doc1", "doc2"])
        assert task_id is not None

        status = await svc.get_task_status(task_id)
        assert status is not None
        assert status["type"] == "reindex"
        assert status["total"] == 2

    @pytest.mark.asyncio
    async def test_regenerate_plans(self) -> None:
        """验证批量重新生成。"""
        svc = BatchTaskService()
        task_id = await svc.regenerate_plans("ws-1", ["prd1"])
        assert task_id is not None

    @pytest.mark.asyncio
    async def test_update_progress(self) -> None:
        """验证进度更新。"""
        svc = BatchTaskService()
        task_id = await svc.reindex_documents("ws-1", ["doc1"])
        await svc.update_progress(task_id, 50)
        status = await svc.get_task_status(task_id)
        assert status is not None
        assert status["progress"] == 50

    @pytest.mark.asyncio
    async def test_get_task_status_nonexistent(self) -> None:
        """验证不存在的任务返回 None。"""
        svc = BatchTaskService()
        assert await svc.get_task_status("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_tasks(self) -> None:
        """验证任务列表。"""
        svc = BatchTaskService()
        await svc.reindex_documents("ws-1", ["doc1"])
        await svc.reindex_documents("ws-1", ["doc2"])
        await svc.reindex_documents("ws-2", ["doc3"])
        tasks = await svc.list_tasks("ws-1")
        assert len(tasks) == 2


class TestBatchScheduler:
    """调度器单元测试。"""

    def test_schedule_config(self) -> None:
        """验证 Celery Beat 配置。"""
        scheduler = BatchScheduler()
        config = scheduler.get_schedule_config()
        assert "refresh-knowledge-graph" in config
        assert "cleanup-expired-sessions" in config
        assert "sync-web-resources" in config

    @pytest.mark.asyncio
    async def test_trigger_known_task(self) -> None:
        """验证触发已知任务。"""
        scheduler = BatchScheduler()
        result = await scheduler.trigger_now("refresh-knowledge-graph")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_trigger_unknown_task(self) -> None:
        """验证触发未知任务返回错误。"""
        scheduler = BatchScheduler()
        result = await scheduler.trigger_now("unknown-task")
        assert result["success"] is False
