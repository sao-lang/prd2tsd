"""异步任务管理器（in-memory 队列）。

使用 asyncio.create_task + in-memory dict 管理任务生命周期，
通过 LangGraph MemorySaver 实现 interrupt/resume 支持。
块 E 将替换为 Celery/Redis 实现。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.logger import get_logger
from app.orchestrator.state import TaskInfo, make_initial_state

logger = get_logger("prd2tsd.task_manager")


class TaskManager:
    """异步任务管理器。

    管理 PRD→TSD 生成任务的创建、执行和状态查询。
    支持 LangGraph interrupt/resume 机制用于人工审核。
    """

    def __init__(self) -> None:
        """初始化任务管理器。"""
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        prd_raw: str,
        prd_file_type: str = "md",
        workspace_id: str = "",
        user_id: str = "",
        user_role: str = "",
        permissions: list[str] | None = None,
        orchestrator: Any = None,
    ) -> str:
        """创建并启动异步生成任务。

        Args:
            prd_raw: PRD 原始内容。
            prd_file_type: 文件类型。
            workspace_id: 工作空间 ID。
            user_id: 用户 ID。
            user_role: 用户角色。
            permissions: 用户权限列表。
            orchestrator: 编译后的主编排 StateGraph（需使用 MemorySaver）。

        Returns:
            任务 ID。
        """
        task_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        task_record: dict[str, Any] = {
            "task_id": task_id,
            "status": "running",
            "progress": 0.0,
            "result": None,
            "evaluation": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            # LangGraph 线程配置，用于 interrupt/resume
            "thread_id": str(uuid.uuid4()),
            "orchestrator": orchestrator,
            "interrupt_stage": None,
        }

        async with self._lock:
            self._tasks[task_id] = task_record

        # 异步执行
        asyncio.create_task(
            self._execute_task(
                task_id=task_id,
                prd_raw=prd_raw,
                prd_file_type=prd_file_type,
                workspace_id=workspace_id,
                user_id=user_id,
                user_role=user_role,
                permissions=permissions or [],
            )
        )

        logger.info("任务已创建: task_id=%s", task_id)
        return task_id

    async def get_task(self, task_id: str) -> TaskInfo | None:
        """查询任务状态。

        Args:
            task_id: 任务 ID。

        Returns:
            任务信息，不存在返回 None。
        """
        async with self._lock:
            record = self._tasks.get(task_id)
        if record is None:
            return None
        return TaskInfo(**record)

    async def get_pending_reviews(self) -> list[TaskInfo]:
        """获取所有待人工审核的任务。

        Returns:
            待审核任务列表。
        """
        async with self._lock:
            pending = [TaskInfo(**r) for r in self._tasks.values() if r["status"] == "paused"]
        return pending

    async def resolve_review(
        self,
        task_id: str,
        stage: str,
        decision: str,
        comment: str = "",
    ) -> bool:
        """处理人工审核结果，恢复被 interrupt 暂停的图执行。

        Args:
            task_id: 任务 ID。
            stage: 审核阶段（analysis / planning）。
            decision: 审核决策（approved / needs_changes）。
            comment: 审核意见。

        Returns:
            是否处理成功。
        """
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return False
            if record["status"] != "paused":
                return False

            record["status"] = "resuming"
            record["updated_at"] = datetime.now(UTC).isoformat()
            orchestrator = record.get("orchestrator")
            thread_id = record.get("thread_id")

        if orchestrator is None:
            logger.error("审核恢复失败: 无 orchestrator 引用 (task=%s)", task_id)
            return False

        # 异步恢复图执行（不阻塞）
        asyncio.create_task(
            self._resume_task(
                task_id=task_id,
                orchestrator=orchestrator,
                thread_id=thread_id,
                resume_value={"decision": decision, "comment": comment},
            )
        )

        logger.info("审核已处理: task=%s, stage=%s, decision=%s", task_id, stage, decision)
        return True

    async def _execute_task(
        self,
        task_id: str,
        prd_raw: str,
        prd_file_type: str,
        workspace_id: str,
        user_id: str,
        user_role: str,
        permissions: list[str],
    ) -> None:
        """异步执行任务（首次运行）。

        Args:
            task_id: 任务 ID。
            prd_raw: PRD 原始内容。
            prd_file_type: 文件类型。
            workspace_id: 工作空间 ID。
            user_id: 用户 ID。
            user_role: 用户角色。
            permissions: 用户权限列表。
        """
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            orchestrator = record.get("orchestrator")
            thread_id = record.get("thread_id")

        if orchestrator is None:
            await self._mark_failed(task_id, "Orchestrator 引用为空")
            return

        try:
            initial_state = make_initial_state(
                task_id=task_id,
                prd_raw=prd_raw,
                prd_file_type=prd_file_type,
                workspace_id=workspace_id,
                user_id=user_id,
                user_role=user_role,
                permissions=permissions,
            )

            # 带线程配置执行（支持 interrupt/resume）
            config = {"configurable": {"thread_id": thread_id}}
            final_state = await orchestrator.ainvoke(initial_state, config)

            # 检查是否是 interrupt 暂停
            if final_state is not None and final_state.get("status") != "running":
                await self._update_result(task_id, final_state)
            else:
                # 图被 interrupt 暂停了（状态保持 running）
                async with self._lock:
                    r = self._tasks.get(task_id)
                    if r:
                        r["status"] = "paused"
                        r["updated_at"] = datetime.now(UTC).isoformat()
                logger.info("任务已暂停等待人工审核: task_id=%s", task_id)

        except Exception as exc:
            await self._mark_failed(task_id, str(exc))

    async def _resume_task(
        self,
        task_id: str,
        orchestrator: Any,
        thread_id: str,
        resume_value: dict[str, str],
    ) -> None:
        """恢复被 interrupt 暂停的任务。

        Args:
            task_id: 任务 ID。
            orchestrator: 编译后的主编排 StateGraph。
            thread_id: LangGraph 线程 ID。
            resume_value: 恢复值（审核决策）。
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            # 向被 interrupt 的节点传递恢复值
            final_state = await orchestrator.ainvoke(resume_value, config)

            if final_state is not None:
                await self._update_result(task_id, final_state)
            else:
                # 可能又被 interrupt 了
                async with self._lock:
                    r = self._tasks.get(task_id)
                    if r:
                        r["status"] = "paused"
                        r["updated_at"] = datetime.now(UTC).isoformat()

        except Exception as exc:
            await self._mark_failed(task_id, str(exc))

    async def _update_result(self, task_id: str, final_state: dict) -> None:
        """更新任务结果为完成状态。

        Args:
            task_id: 任务 ID。
            final_state: Orchestrator 最终状态。
        """
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record["status"] = final_state.get("status", "complete")
                record["progress"] = final_state.get("progress", 1.0)
                record["result"] = final_state.get("generation_result")
                record["evaluation"] = final_state.get("evaluation_report")
                record["updated_at"] = datetime.now(UTC).isoformat()

        logger.info("任务执行完成: task_id=%s, status=%s", task_id, final_state.get("status"))

    async def _mark_failed(self, task_id: str, error: str) -> None:
        """标记任务为失败。

        Args:
            task_id: 任务 ID。
            error: 错误信息。
        """
        logger.error("任务执行失败: task_id=%s, error=%s", task_id, error)
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record["status"] = "failed"
                record["error"] = error
                record["updated_at"] = datetime.now(UTC).isoformat()


# 全局单例
task_manager = TaskManager()
