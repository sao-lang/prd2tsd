"""统一任务队列 — 支持优先级 + 取消 + 持久化。

使用 heapq 实现优先级队列，高优先级的任务先出队。
支持 PostgreSQL 持久化（重启不丢失）。
"""

from __future__ import annotations

import asyncio
import heapq
import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logger import get_logger
from contracts.models import Task, TaskStatus

logger = get_logger("prd2tsd.task_queue")


class TaskQueue:
    """统一任务队列 — 支持优先级 + 取消 + 持久化。

    使用 heapq 实现优先级队列，高优先级的任务先出队。
    支持 PostgreSQL 持久化（重启不丢失）。
    """

    def __init__(self, db_session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        """初始化任务队列。

        Args:
            db_session_factory: 数据库异步会话工厂（可选，用于持久化）。
        """
        self._mem_queue: list[tuple[int, float, Task]] = []  # (priority, time, task)
        self._running: dict[str, asyncio.Task[Any]] = {}  # 正在执行的任务
        self._running_task_info: dict[str, Task] = {}  # 正在执行的任务信息
        self._session_factory = db_session_factory
        self._lock = asyncio.Lock()
        self._table_ready = False

    async def enqueue(self, task: Task) -> None:
        """入队。优先级越小越先执行。

        Args:
            task: 任务对象。
        """
        async with self._lock:
            heapq.heappush(self._mem_queue, (task.priority, time.monotonic(), task))
            await self._persist(task)
            logger.info("任务入队: %s (type=%s, priority=%d)", task.id, task.type, task.priority)

    async def dequeue(self) -> Task | None:
        """出队 — 取优先级最高的任务。

        Returns:
            优先级最高的任务，队列为空返回 None。
        """
        async with self._lock:
            if not self._mem_queue:
                return None
            _, _, task = heapq.heappop(self._mem_queue)
            return task

    async def cancel(self, task_id: str) -> bool:
        """取消任务。

        - 队列中未执行 → 从队列移除
        - 正在执行 → 取消 asyncio.Task

        Args:
            task_id: 任务 ID。

        Returns:
            是否成功取消。
        """
        async with self._lock:
            # 检查是否在队列中
            for i, (_, _, t) in enumerate(self._mem_queue):
                if t.id == task_id:
                    self._mem_queue.pop(i)
                    heapq.heapify(self._mem_queue)
                    await self._update_status(task_id, TaskStatus.CANCELLED)
                    logger.info("任务已取消（队列中）: %s", task_id)
                    return True
            # 检查是否正在运行
            running_task = self._running.get(task_id)
            if running_task:
                running_task.cancel()
                self._running.pop(task_id, None)
                self._running_task_info.pop(task_id, None)
                await self._update_status(task_id, TaskStatus.CANCELLED)
                logger.info("任务已取消（运行中）: %s", task_id)
                return True
        return False

    async def get_status(self, task_id: str) -> Task | None:
        """查询任务状态。

        Args:
            task_id: 任务 ID。

        Returns:
            任务信息，不存在返回 None。
        """
        async with self._lock:
            for _, _, t in self._mem_queue:
                if t.id == task_id:
                    return t
            running_task = self._running_task_info.get(task_id)
            if running_task:
                return running_task
        return await self._load_from_db(task_id)

    async def _ensure_table(self) -> None:
        """确保 tasks 表已创建。"""
        if self._table_ready or not self._session_factory:
            return
        session_factory = self._session_factory
        async with session_factory() as session:
            await session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id VARCHAR(64) PRIMARY KEY,
                    type VARCHAR(32) NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    progress REAL NOT NULL DEFAULT 0.0,
                    total_steps INTEGER NOT NULL DEFAULT 1,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    workspace_id VARCHAR(64) NOT NULL DEFAULT '',
                    user_id VARCHAR(64) NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    result JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    cancellable BOOLEAN NOT NULL DEFAULT TRUE,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    metadata JSONB NOT NULL DEFAULT '{}'
                )
                """)
            )
            # workspace_id 查询索引
            await session.execute(
                text("CREATE INDEX IF NOT EXISTS idx_tasks_workspace_id ON tasks(workspace_id)")
            )
            # 状态查询索引
            await session.execute(
                text("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            )
            await session.commit()
            self._table_ready = True
            logger.info("tasks 表已就绪")

    async def _get_session(self) -> AsyncSession:
        """获取数据库会话。"""
        session_factory = self._session_factory
        if not session_factory:
            raise RuntimeError("_session_factory 未配置，无法持久化")
        return session_factory()

    def _task_to_row(self, task: Task) -> dict[str, Any]:
        """将 Task 对象转为数据库行。"""
        return {
            "id": task.id,
            "type": task.type.value if hasattr(task.type, "value") else str(task.type),
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "priority": task.priority,
            "progress": task.progress,
            "total_steps": task.total_steps,
            "current_step": task.current_step,
            "workspace_id": task.workspace_id,
            "user_id": task.user_id,
            "error_message": task.error_message,
            "result": json.dumps(task.result, ensure_ascii=False, default=str),
            "created_at": task.created_at,
            "updated_at": datetime.now(UTC),
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "cancellable": task.cancellable,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "metadata": json.dumps(task.metadata, ensure_ascii=False, default=str),
        }

    @staticmethod
    def _row_to_task(row: Any) -> Task:
        """将数据库行转为 Task 对象。"""
        row_dict = dict(row._mapping)
        # 解析 JSONB 字段
        for json_field in ("result", "metadata"):
            val = row_dict.get(json_field)
            if isinstance(val, str):
                row_dict[json_field] = json.loads(val)
        # 确保必填字段
        for f in ("result", "metadata"):
            if not isinstance(row_dict.get(f), dict):
                row_dict[f] = {}
        return Task(**row_dict)

    async def _persist(self, task: Task) -> None:
        """持久化到 PostgreSQL — INSERT ON CONFLICT UPDATE。

        Args:
            task: 待持久化的任务对象。
        """
        if not self._session_factory:
            return
        await self._ensure_table()
        session = await self._get_session()
        row = self._task_to_row(task)
        await session.execute(
            text("""
            INSERT INTO tasks (
                id, type, status, priority, progress, total_steps, current_step,
                workspace_id, user_id, error_message, result,
                created_at, updated_at, started_at, completed_at,
                cancellable, retry_count, max_retries, metadata
            ) VALUES (
                :id, :type, :status, :priority, :progress, :total_steps, :current_step,
                :workspace_id, :user_id, :error_message, :result::jsonb,
                :created_at, :updated_at, :started_at, :completed_at,
                :cancellable, :retry_count, :max_retries, :metadata::jsonb
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                priority = EXCLUDED.priority,
                progress = EXCLUDED.progress,
                current_step = EXCLUDED.current_step,
                error_message = EXCLUDED.error_message,
                result = EXCLUDED.result,
                updated_at = EXCLUDED.updated_at,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                retry_count = EXCLUDED.retry_count,
                metadata = EXCLUDED.metadata
            """),
            row,
        )
        await session.commit()

    async def _update_status(self, task_id: str, status: TaskStatus) -> None:
        """更新任务状态（持久化）。

        Args:
            task_id: 任务 ID。
            status: 新状态。
        """
        if not self._session_factory:
            return
        await self._ensure_table()
        session = await self._get_session()
        status_value = status.value if hasattr(status, "value") else str(status)
        now = datetime.now(UTC)
        await session.execute(
            text("""
            UPDATE tasks
            SET status = :status, updated_at = :now,
                completed_at = CASE WHEN :status IN ('completed','failed','cancelled') THEN :now ELSE completed_at END
            WHERE id = :task_id
            """),
            {"task_id": task_id, "status": status_value, "now": now},
        )
        await session.commit()

    async def _load_from_db(self, task_id: str) -> Task | None:
        """从数据库加载任务。

        Args:
            task_id: 任务 ID。

        Returns:
            加载的 Task 对象，不存在返回 None。
        """
        if not self._session_factory:
            return None
        await self._ensure_table()
        session = await self._get_session()
        result = await session.execute(
            text("SELECT * FROM tasks WHERE id = :task_id"),
            {"task_id": task_id},
        )
        row = result.one_or_none()
        if row is None:
            return None
        return self._row_to_task(row)

    def get_queue_size(self) -> int:
        """获取队列大小。"""
        return len(self._mem_queue)

    def get_running_count(self) -> int:
        """获取正在运行的任务数。"""
        return len(self._running)
