"""生成路由 — GET /api/v1/tasks/{task_id} 任务状态查询。

POST /api/v1/generate 已由统一交互入口 /api/v1/interact 的
complex_generation 意图替代（Block E B1）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.deps import get_current_user
from app.models.user import User
from app.orchestrator.state import TaskInfo
from app.task_manager import task_manager

router = APIRouter(prefix="/api/v1", tags=["generate"])


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> TaskInfo:
    """查询任务状态和结果。

    Args:
        task_id: 任务 ID。
        current_user: 当前用户。

    Returns:
        任务状态信息。

    Raises:
        HTTPException: 任务不存在时返回 404。
    """
    task = await task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
