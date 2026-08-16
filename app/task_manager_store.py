"""TaskManager 持久化存储 — task_runs 表读写（重启后可恢复任务索引与断点）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.models.persistence import TaskRun

logger = get_logger("prd2tsd.task_store")


def _dump(value: Any) -> Any:
    """将 Pydantic 模型序列化为 dict（供 JSON 列存储）。"""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return str(value)


async def create_task_run(record: dict[str, Any]) -> None:
    """写入一条任务运行记录（失败仅告警，不影响主流程）。"""
    try:
        pg = connection_manager.get("postgres")
        now = datetime.now(UTC)
        async with pg.get_session() as db:
            db.add(
                TaskRun(
                    task_id=str(record.get("task_id", "")),
                    thread_id=record.get("thread_id"),
                    session_id=record.get("session_id"),
                    workspace_id=record.get("workspace_id"),
                    user_id=record.get("user_id"),
                    status=str(record.get("status", "running")),
                    progress=float(record.get("progress", 0.0)),
                    stage=str(record.get("stage", "")),
                    interrupt_stage=str(record.get("interrupt_stage", "")),
                    result=_dump(record.get("result")),
                    evaluation=_dump(record.get("evaluation")),
                    error=record.get("error"),
                    created_at=now,
                    updated_at=now,
                )
            )
            await db.commit()
    except Exception as exc:
        logger.warning("任务持久化创建失败（任务仍在内存储存）: task=%s, error=%s", record.get("task_id"), exc)


async def update_task_run(task_id: str, **fields: Any) -> None:
    """更新任务运行记录（失败仅告警）。"""
    if not task_id:
        return
    try:
        from sqlalchemy import update

        pg = connection_manager.get("postgres")
        async with pg.get_session() as db:
            values: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
            if "result" in values:
                values["result"] = _dump(values["result"])
            if "evaluation" in values:
                values["evaluation"] = _dump(values["evaluation"])
            values["updated_at"] = datetime.now(UTC)
            await db.execute(update(TaskRun).where(TaskRun.task_id == task_id).values(**values))
            await db.commit()
    except Exception as exc:
        logger.warning("任务持久化更新失败: task=%s, error=%s", task_id, exc)


async def load_task_run(task_id: str) -> dict[str, Any] | None:
    """按 task_id 加载任务记录（无记录或 DB 不可用时返回 None）。"""
    try:
        pg = connection_manager.get("postgres")
        async with pg.get_session() as db:
            result = await db.execute(select(TaskRun).where(TaskRun.task_id == task_id))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "task_id": row.task_id,
                "thread_id": row.thread_id or "",
                "session_id": row.session_id or "",
                "workspace_id": row.workspace_id or "",
                "user_id": row.user_id or "",
                "status": row.status,
                "progress": row.progress,
                "stage": row.stage,
                "interrupt_stage": row.interrupt_stage,
                "result": row.result,
                "evaluation": row.evaluation,
                "error": row.error,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "updated_at": row.updated_at.isoformat() if row.updated_at else "",
            }
    except Exception as exc:
        logger.warning("任务持久化读取失败: task=%s, error=%s", task_id, exc)
        return None


async def load_paused_task_ids() -> list[str]:
    """加载所有 paused 任务 ID（人工审核恢复列表）。"""
    try:
        pg = connection_manager.get("postgres")
        async with pg.get_session() as db:
            result = await db.execute(
                select(TaskRun.task_id).where(TaskRun.status == "paused").order_by(TaskRun.updated_at.desc())
            )
            return [r for (r,) in result.all()]
    except Exception as exc:
        logger.warning("加载暂停任务列表失败: %s", exc)
        return []
