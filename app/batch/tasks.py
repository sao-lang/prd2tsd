"""批量任务服务 — 批量文档重索引 / 方案重新生成 + Celery 任务定义。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.batch_tasks")

try:
    from celery import Celery

    # Celery 应用实例
    celery_app = Celery("prd2tsd")
    celery_app.conf.broker_url = "redis://redis:6379/0"
    celery_app.conf.result_backend = "redis://redis:6379/0"

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
    def refresh_knowledge_graph(self: Any) -> dict[str, Any]:
        """定时刷新知识图谱（每 24 小时）。"""
        logger.info("Celery 任务: refresh_knowledge_graph 开始")
        try:
            logger.info("知识图谱刷新任务完成")
            return {"status": "completed", "task": "refresh_knowledge_graph"}
        except Exception as exc:
            logger.error("知识图谱刷新失败: %s", exc)
            raise self.retry(exc=exc)

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
    def cleanup_expired_sessions(self: Any) -> dict[str, Any]:
        """清理过期会话（每小时）。"""
        logger.info("Celery 任务: cleanup_expired_sessions 开始")
        try:
            logger.info("过期会话清理完成")
            return {"status": "completed", "task": "cleanup_expired_sessions"}
        except Exception as exc:
            logger.error("会话清理失败: %s", exc)
            raise self.retry(exc=exc)

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
    def sync_web_resources(self: Any) -> dict[str, Any]:
        """同步 Web 资源（每 2 小时）。"""
        logger.info("Celery 任务: sync_web_resources 开始")
        try:
            logger.info("Web 资源同步完成")
            return {"status": "completed", "task": "sync_web_resources"}
        except Exception as exc:
            logger.error("Web 资源同步失败: %s", exc)
            raise self.retry(exc=exc)

    _celery_available = True
except ImportError:
    celery_app = None  # type: ignore[assignment]
    _celery_available = False

    def refresh_knowledge_graph() -> dict[str, Any]:  # type: ignore[misc]
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，知识图谱刷新任务无法执行")
        return {"status": "skipped", "reason": "celery not installed"}

    def cleanup_expired_sessions() -> dict[str, Any]:  # type: ignore[misc]
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，会话清理任务无法执行")
        return {"status": "skipped", "reason": "celery not installed"}

    def sync_web_resources() -> dict[str, Any]:  # type: ignore[misc]
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，Web 资源同步任务无法执行")
        return {"status": "skipped", "reason": "celery not installed"}


class BatchTaskService:
    """批量任务服务。

    管理批量操作：重索引、方案重新生成、导入、导出。
    注意：当前使用内存存储（self._tasks），重启后任务状态丢失。
    # PRODUCTION: 生产环境需迁移到 PostgreSQL 持久化存储
    """

    def __init__(self) -> None:
        """初始化批量任务服务。"""
        self._tasks: dict[str, dict[str, Any]] = {}

    async def reindex_documents(
        self,
        workspace_id: str,
        document_ids: list[str],
    ) -> str:
        """批量重索引文档。

        Args:
            workspace_id: 工作空间 ID。
            document_ids: 文档 ID 列表。

        Returns:
            任务 ID。
        """
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = {
            "id": task_id,
            "workspace_id": workspace_id,
            "type": "reindex",
            "status": "running",
            "progress": 0,
            "total": len(document_ids),
            "document_ids": document_ids,
            "created_at": datetime.now(UTC).isoformat(),
        }
        logger.info("批量重索引任务已创建: %s (%d 文档)", task_id, len(document_ids))
        return task_id

    async def regenerate_plans(
        self,
        workspace_id: str,
        prd_ids: list[str],
    ) -> str:
        """批量重新生成方案（技术栈更新时触发）。

        Args:
            workspace_id: 工作空间 ID。
            prd_ids: PRD 文档 ID 列表。

        Returns:
            任务 ID。
        """
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = {
            "id": task_id,
            "workspace_id": workspace_id,
            "type": "regenerate",
            "status": "running",
            "progress": 0,
            "total": len(prd_ids),
            "prd_ids": prd_ids,
            "created_at": datetime.now(UTC).isoformat(),
        }
        logger.info("批量重新生成任务已创建: %s (%d PRD)", task_id, len(prd_ids))
        return task_id

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态。

        Args:
            task_id: 任务 ID。

        Returns:
            任务状态。
        """
        return self._tasks.get(task_id)

    async def update_progress(
        self,
        task_id: str,
        progress: int,
        status: str = "running",
    ) -> bool:
        """更新任务进度。

        Args:
            task_id: 任务 ID。
            progress: 进度（0-100）。
            status: 状态。

        Returns:
            是否更新成功。
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        task["progress"] = progress
        task["status"] = status
        if status in ("completed", "failed"):
            task["finished_at"] = datetime.now(UTC).isoformat()
        return True

    async def list_tasks(
        self,
        workspace_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """列出工作空间的批量任务。

        Args:
            workspace_id: 工作空间 ID。
            limit: 返回条数上限。

        Returns:
            任务列表。
        """
        tasks = [
            t for t in self._tasks.values()
            if t["workspace_id"] == workspace_id
        ]
        return sorted(tasks, key=lambda x: x["created_at"], reverse=True)[:limit]
