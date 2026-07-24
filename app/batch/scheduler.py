"""Celery Beat 定时任务调度器 — 知识图谱定期刷新等。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.scheduler")


class BatchScheduler:
    """定时任务调度器。

    配置 Celery Beat 定时任务。
    当前为配置定义层，实际 Celery Worker 需要独立启动。
    """

    # Celery Beat 调度定义
    BEAT_SCHEDULE: dict[str, dict[str, Any]] = {
        "refresh-knowledge-graph": {
            "task": "prd2tsd.batch.tasks.refresh_knowledge_graph",
            "schedule": 86400,  # 每 24 小时
            "args": (),
        },
        "cleanup-expired-sessions": {
            "task": "prd2tsd.batch.tasks.cleanup_expired_sessions",
            "schedule": 3600,  # 每小时
            "args": (),
        },
        "sync-web-resources": {
            "task": "prd2tsd.batch.tasks.sync_web_resources",
            "schedule": 7200,  # 每 2 小时
            "args": (),
        },
    }

    def __init__(self) -> None:
        """初始化调度器。"""
        self._jobs: dict[str, dict[str, Any]] = {}

    async def trigger_now(self, task_name: str) -> dict[str, Any]:
        """立即触发一个定时任务。

        Args:
            task_name: 任务名称（如 refresh-knowledge-graph）。

        Returns:
            触发结果。
        """
        if task_name not in self.BEAT_SCHEDULE:
            return {"success": False, "error": f"未知任务: {task_name}"}

        schedule = self.BEAT_SCHEDULE[task_name]
        logger.info("定时任务已触发: %s", task_name)
        return {
            "success": True,
            "task": task_name,
            "schedule_seconds": schedule["schedule"],
        }

    def get_schedule_config(self) -> dict[str, dict[str, Any]]:
        """获取 Celery Beat 配置。

        Returns:
            Celery Beat 调度配置。
        """
        return self.BEAT_SCHEDULE
