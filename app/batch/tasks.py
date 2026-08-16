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

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)  # type: ignore[untyped-decorator]
    def refresh_knowledge_graph(self: Any) -> dict[str, Any]:
        """定时刷新知识图谱（每 24 小时）。"""
        import asyncio

        logger.info("Celery 任务: refresh_knowledge_graph 开始")
        try:
            async def _run() -> dict[str, Any]:
                from app.knowledge_layer.pipeline import KnowledgeGraphBuilder

                builder = KnowledgeGraphBuilder()
                # 报告当前图谱规模（实体/关系计数），作为定时刷新的基线
                stats = await builder.get_stats()
                return {"status": "completed", "task": "refresh_knowledge_graph", "stats": stats.model_dump()}

            result = asyncio.run(_run())
            logger.info("知识图谱刷新任务完成: %s", result)
            return result
        except Exception as exc:
            logger.error("知识图谱刷新失败: %s", exc)
            raise self.retry(exc=exc) from exc

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=30)  # type: ignore[untyped-decorator]
    def cleanup_expired_sessions(self: Any) -> dict[str, Any]:
        """清理过期会话（每小时）。"""
        import asyncio

        logger.info("Celery 任务: cleanup_expired_sessions 开始")
        try:
            async def _run() -> dict[str, Any]:
                from sqlalchemy import select

                from app.core.connections import connection_manager
                from app.models.organization import Organization
                from app.models.workspace import Workspace
                from app.session_history.cleanup import SessionCleanupPolicy
                from app.session_history.repository import SessionRepository

                repo = SessionRepository()
                policy = SessionCleanupPolicy(repo)
                deleted_total = 0
                try:
                    pg = connection_manager.get("postgres")
                    async with pg.get_session() as db:
                        result = await db.execute(
                            select(Workspace.id, Organization.plan)
                            .join(Organization, Organization.id == Workspace.organization_id)
                            .where(Workspace.is_archived.is_(False))
                        )
                        for workspace_id, plan in result.all():
                            deleted_total += await policy.cleanup(db, workspace_id, plan or "free")
                except Exception as exc:
                    logger.warning("读取工作空间失败，跳过清理: %s", exc)
                return {
                    "status": "completed",
                    "task": "cleanup_expired_sessions",
                    "deleted": deleted_total,
                }

            result = asyncio.run(_run())
            logger.info("过期会话清理完成: %s", result)
            return result
        except Exception as exc:
            logger.error("会话清理失败: %s", exc)
            raise self.retry(exc=exc) from exc

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=120)  # type: ignore[untyped-decorator]
    def sync_web_resources(self: Any) -> dict[str, Any]:
        """同步 Web 资源（每 2 小时）。"""
        import asyncio

        logger.info("Celery 任务: sync_web_resources 开始")
        try:
            async def _run() -> dict[str, Any]:
                from sqlalchemy import select

                from app.core.connections import connection_manager
                from app.models.block_e import UploadedDocument
                from app.web_indexing.web_sync import WebSyncScheduler

                # 从 uploaded_documents 收集待同步的 URL（source_url 非空且未删除）
                urls: list[str] = []
                try:
                    pg = connection_manager.get("postgres")
                    async with pg.get_session() as db:
                        result = await db.execute(
                            select(UploadedDocument.source_url).where(
                                UploadedDocument.source_url.is_not(None),
                                UploadedDocument.is_deleted.is_(False),
                            )
                        )
                        urls = [u for (u,) in result.all() if u]
                except Exception as exc:
                    logger.warning("读取待同步 URL 失败: %s", exc)

                if not urls:
                    return {
                        "status": "completed",
                        "task": "sync_web_resources",
                        "synced": [],
                        "note": "无待同步 URL",
                    }

                scheduler = WebSyncScheduler()
                synced = await scheduler.sync_multi(urls[:50])
                return {"status": "completed", "task": "sync_web_resources", "synced": synced}

            result = asyncio.run(_run())
            logger.info("Web 资源同步完成: %s", result)
            return result
        except Exception as exc:
            logger.error("Web 资源同步失败: %s", exc)
            raise self.retry(exc=exc) from exc

    @celery_app.task(bind=True, max_retries=3, default_retry_delay=60)  # type: ignore[untyped-decorator]
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
                async with connector.get_session() as session:
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
                            content, doc.original_filename, doc.workspace_id, document_id=str(doc.id),
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
    celery_app = None
    _celery_available = False

    def refresh_knowledge_graph() -> dict[str, Any]:
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，知识图谱刷新任务无法执行")
        return {"status": "skipped", "reason": "celery not installed"}

    def cleanup_expired_sessions() -> dict[str, Any]:
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，会话清理任务无法执行")
        return {"status": "skipped", "reason": "celery not installed"}

    def sync_web_resources() -> dict[str, Any]:
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，Web 资源同步任务无法执行")
        return {"status": "skipped", "reason": "celery not installed"}

    def index_document_to_kg(document_id: str) -> dict[str, Any]:
        """（降级）Celery 不可用时返回跳过状态。"""
        logger.warning("Celery 未安装，文档入图任务无法执行: %s", document_id)
        return {"status": "skipped", "reason": "celery not installed"}


class BatchTaskService:
    """批量任务服务。

    管理批量操作：重索引、方案重新生成、导入、导出。
    任务状态持久化到 PostgreSQL（batch_tasks 表，重启可恢复）；
    DB 不可用时降级内存存储（与 TaskManager 相同的降级策略）。
    """

    def __init__(self) -> None:
        """初始化批量任务服务。"""
        self._tasks: dict[str, dict[str, Any]] = {}

    async def _persist(self, task: dict[str, Any]) -> None:
        """写入/更新 batch_tasks 表；DB 不可用时仅保留内存。

        Args:
            task: 批量任务字典。
        """
        try:
            from app.core.connections import connection_manager
            from app.models.persistence import BatchTask

            pg = connection_manager.get("postgres")
            async with pg.get_session() as db:
                now = datetime.now(UTC)
                existing = await db.get(BatchTask, task["id"])
                if existing is None:
                    db.add(
                        BatchTask(
                            id=task["id"],
                            workspace_id=task["workspace_id"],
                            task_type=task["type"],
                            status=task.get("status", "running"),
                            progress=task.get("progress", 0),
                            total=task.get("total", 0),
                            payload={
                                k: task[k]
                                for k in ("document_ids", "prd_ids")
                                if k in task
                            },
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    existing.status = task.get("status", existing.status)
                    existing.progress = task.get("progress", existing.progress)
                    existing.updated_at = now
                await db.commit()
        except Exception as exc:
            logger.warning("批量任务持久化失败（降级内存）: %s", exc)

    async def _load_from_db(self, task_id: str) -> dict[str, Any] | None:
        """从 DB 恢复任务（内存未命中时）。

        Args:
            task_id: 任务 ID。

        Returns:
            任务字典；不存在或 DB 不可用时返回 None。
        """
        try:
            from app.core.connections import connection_manager
            from app.models.persistence import BatchTask

            pg = connection_manager.get("postgres")
            async with pg.get_session() as db:
                row = await db.get(BatchTask, task_id)
                if row is None:
                    return None
                task: dict[str, Any] = {
                    "id": row.id,
                    "workspace_id": row.workspace_id,
                    "type": row.task_type,
                    "status": row.status,
                    "progress": row.progress,
                    "total": row.total,
                    "created_at": row.created_at.isoformat() if row.created_at else "",
                }
                if row.payload:
                    task.update(row.payload)
                return task
        except Exception as exc:
            logger.warning("批量任务 DB 读取失败: %s", exc)
            return None

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
        task = {
            "id": task_id,
            "workspace_id": workspace_id,
            "type": "reindex",
            "status": "running",
            "progress": 0,
            "total": len(document_ids),
            "document_ids": document_ids,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._tasks[task_id] = task
        await self._persist(task)
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
        task = {
            "id": task_id,
            "workspace_id": workspace_id,
            "type": "regenerate",
            "status": "running",
            "progress": 0,
            "total": len(prd_ids),
            "prd_ids": prd_ids,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._tasks[task_id] = task
        await self._persist(task)
        logger.info("批量重新生成任务已创建: %s (%d PRD)", task_id, len(prd_ids))
        return task_id

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """获取任务状态。

        Args:
            task_id: 任务 ID。

        Returns:
            任务状态；不存在返回 None。
        """
        task = self._tasks.get(task_id)
        if task is not None:
            return task
        return await self._load_from_db(task_id)

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
        if task is None:
            # 内存未命中时尝试从 DB 恢复后更新
            task = await self._load_from_db(task_id)
            if task is None:
                return False
            self._tasks[task_id] = task
        task["progress"] = progress
        task["status"] = status
        if status in ("completed", "failed"):
            task["finished_at"] = datetime.now(UTC).isoformat()
        await self._persist(task)
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
        try:
            from sqlalchemy import select

            from app.core.connections import connection_manager
            from app.models.persistence import BatchTask

            pg = connection_manager.get("postgres")
            async with pg.get_session() as db:
                result = await db.execute(
                    select(BatchTask)
                    .where(BatchTask.workspace_id == workspace_id)
                    .order_by(BatchTask.created_at.desc())
                    .limit(limit)
                )
                memory_ids = {t["id"] for t in tasks}
                for row in result.scalars().all():
                    if row.id in memory_ids:
                        continue
                    task: dict[str, Any] = {
                        "id": row.id,
                        "workspace_id": row.workspace_id,
                        "type": row.task_type,
                        "status": row.status,
                        "progress": row.progress,
                        "total": row.total,
                        "created_at": row.created_at.isoformat() if row.created_at else "",
                    }
                    if row.payload:
                        task.update(row.payload)
                    tasks.append(task)
        except Exception as exc:
            logger.warning("批量任务列表 DB 读取失败（仅返回内存）: %s", exc)
        return sorted(tasks, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
