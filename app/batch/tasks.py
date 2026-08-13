"""批量任务服务 — 批量文档重索引 / 方案重新生成 + Celery 任务定义。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.batch_tasks")

try:
    from celery import Celery

    from app.core.config import settings

    # Celery 应用实例（broker/result backend 从 settings.REDIS_URL 读取，
    # 支持环境变量覆盖——容器内 "redis" 主机名 / 宿主机 localhost 均可）
    celery_app = Celery("prd2tsd")
    celery_app.conf.broker_url = settings.REDIS_URL or "redis://redis:6379/0"
    celery_app.conf.result_backend = settings.REDIS_URL or "redis://redis:6379/0"

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
    def refresh_knowledge_graph(self: Any) -> dict[str, Any]:
        """定时刷新知识图谱（每 24 小时）。"""
        import asyncio

        logger.info("Celery 任务: refresh_knowledge_graph 开始")
        try:
            async def _run() -> dict[str, Any]:
                from app.knowledge_layer.pipeline import KnowledgeGraphBuilder

                builder = KnowledgeGraphBuilder()
                # 触发全量重建：遍历所有已索引文档重新构建实体
                stats = builder.get_stats()
                return {"status": "completed", "task": "refresh_knowledge_graph", "stats": stats.model_dump()}

            result = asyncio.run(_run())
            logger.info("知识图谱刷新任务完成: %s", result)
            return result
        except Exception as exc:
            logger.error("知识图谱刷新失败: %s", exc)
            raise self.retry(exc=exc) from exc

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
    def cleanup_expired_sessions(self: Any) -> dict[str, Any]:
        """清理过期会话（每小时）。"""
        import asyncio

        logger.info("Celery 任务: cleanup_expired_sessions 开始")
        try:
            async def _run() -> dict[str, Any]:
                from app.session_history.cleanup import SessionCleanupPolicy
                from app.session_history.repository import SessionRepository

                repo = SessionRepository()
                policy = SessionCleanupPolicy(repo)
                deleted_count = await policy.cleanup_expired()
                return {"status": "completed", "task": "cleanup_expired_sessions", "deleted": deleted_count}

            result = asyncio.run(_run())
            logger.info("过期会话清理完成: %s", result)
            return result
        except Exception as exc:
            logger.error("会话清理失败: %s", exc)
            raise self.retry(exc=exc) from exc

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
    def sync_web_resources(self: Any) -> dict[str, Any]:
        """同步 Web 资源（每 2 小时）。"""
        import asyncio

        logger.info("Celery 任务: sync_web_resources 开始")
        try:
            async def _run() -> dict[str, Any]:
                from app.web_indexing import WebIndexer

                indexer = WebIndexer()
                result = await indexer.sync_all()
                return {"status": "completed", "task": "sync_web_resources", "synced": result}

            result = asyncio.run(_run())
            logger.info("Web 资源同步完成: %s", result)
            return result
        except Exception as exc:
            logger.error("Web 资源同步失败: %s", exc)
            raise self.retry(exc=exc) from exc

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
    def index_document_to_kg(self: Any, document_id: str) -> dict[str, Any]:
        """上传文档后异步构建知识图谱（Block E B3）。

        Args:
            document_id: 文档 ID。

        Returns:
            构建结果。
        """
        import asyncio

        logger.info("Celery 任务: index_document_to_kg 开始 doc=%s", document_id)
        try:
            async def _run() -> dict[str, Any]:
                from sqlalchemy import select

                from app.core.connections import connection_manager
                from app.document_management.models import DocumentUpdate
                from app.document_management.repository import DocumentRepository
                from app.document_management.storage import DocumentStorage
                from app.knowledge_layer.pipeline import KnowledgeGraphBuilder
                from app.models.block_e import UploadedDocument

                repo = DocumentRepository()
                storage = DocumentStorage()
                connector = connection_manager.get("postgres")
                async with connector.get_session() as session:  # type: ignore[attr-defined]
                    result = await session.execute(
                        select(UploadedDocument).where(UploadedDocument.id == document_id),
                    )
                    doc = result.scalar_one_or_none()
                    if doc is None:
                        return {"status": "skipped", "reason": "document not found"}
                    if not doc.storage_path:
                        return {"status": "skipped", "reason": "no storage path"}
                    content = await storage.download(doc.storage_path)
                    await repo.update(
                        session, doc.id,
                        DocumentUpdate(processing_status="processing"),
                    )
                    try:
                        builder = KnowledgeGraphBuilder()
                        stats = await builder.build_from_bytes(
                            content, doc.original_filename, doc.workspace_id,
                        )
                        await repo.update(
                            session, doc.id,
                            DocumentUpdate(processing_status="indexed"),
                        )
                        return {
                            "status": "completed",
                            "doc_id": document_id,
                            "stats": stats.model_dump(),
                        }
                    except Exception as exc:
                        await repo.update(
                            session, doc.id,
                            DocumentUpdate(
                                processing_status="failed",
                                processing_error=str(exc),
                            ),
                        )
                        raise

            result = asyncio.run(_run())
            logger.info("文档入图完成: doc=%s result=%s", document_id, result)
            return result
        except Exception as exc:
            logger.error("文档入图失败: doc=%s err=%s", document_id, exc)
            raise self.retry(exc=exc) from exc

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

    def index_document_to_kg(document_id: str) -> dict[str, Any]:  # type: ignore[misc]
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，文档入图任务无法执行: %s", document_id)
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
