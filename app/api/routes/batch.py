"""批量处理 API 路由 — 批量重索引/重新生成/定时任务。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.schemas.batch import (
    BatchRegenerateRequest,
    BatchReindexRequest,
    TaskStatusResponse,
)
from app.auth.deps import get_current_user
from app.auth.middleware import _SCOPE_WS_ID as _SCOPE_WORKSPACE_ID
from app.batch.scheduler import BatchScheduler
from app.batch.tasks import BatchTaskService

router = APIRouter(prefix="/api/v1/batch", tags=["batch"])


def _get_workspace_id(request: Request) -> str:
    ws_id = request.scope.get(_SCOPE_WORKSPACE_ID)
    if not ws_id:
        raise HTTPException(status_code=400, detail="缺少工作空间上下文")
    return ws_id


@router.post("/reindex", status_code=201)
async def batch_reindex(
    request: Request,
    req: BatchReindexRequest,
    user_id: str = Depends(get_current_user),
    svc: BatchTaskService = Depends(lambda: BatchTaskService()),
) -> dict:
    """批量重索引文档。

    Args:
        request: FastAPI 请求。
        req: 文档 ID 列表。
        user_id: 当前用户 ID。
        svc: 批量任务服务。

    Returns:
        任务信息。
    """
    ws_id = _get_workspace_id(request)
    task_id = await svc.reindex_documents(ws_id, req.document_ids)
    return {"task_id": task_id, "status": "created", "type": "reindex"}


@router.post("/regenerate", status_code=201)
async def batch_regenerate(
    request: Request,
    req: BatchRegenerateRequest,
    user_id: str = Depends(get_current_user),
    svc: BatchTaskService = Depends(lambda: BatchTaskService()),
) -> dict:
    """批量重新生成方案。

    Args:
        request: FastAPI 请求。
        req: PRD ID 列表。
        user_id: 当前用户 ID。
        svc: 批量任务服务。

    Returns:
        任务信息。
    """
    ws_id = _get_workspace_id(request)
    task_id = await svc.regenerate_plans(ws_id, req.prd_ids)
    return {"task_id": task_id, "status": "created", "type": "regenerate"}


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    svc: BatchTaskService = Depends(lambda: BatchTaskService()),
) -> TaskStatusResponse:
    """获取任务状态。

    Args:
        task_id: 任务 ID。
        svc: 批量任务服务。

    Returns:
        任务状态。
    """
    task = await svc.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusResponse(**task)


@router.get("/tasks", response_model=list[TaskStatusResponse])
async def list_tasks(
    request: Request,
    svc: BatchTaskService = Depends(lambda: BatchTaskService()),
) -> list[TaskStatusResponse]:
    """列出批量任务。

    Args:
        request: FastAPI 请求。
        svc: 批量任务服务。

    Returns:
        任务列表。
    """
    ws_id = _get_workspace_id(request)
    tasks = await svc.list_tasks(ws_id)
    return [TaskStatusResponse(**t) for t in tasks]


@router.post("/scheduler/trigger/{task_name}")
async def trigger_scheduled_task(
    task_name: str,
    user_id: str = Depends(get_current_user),
    scheduler: BatchScheduler = Depends(lambda: BatchScheduler()),
) -> dict:
    """立即触发定时任务。

    Args:
        task_name: 任务名。
        user_id: 当前用户 ID。
        scheduler: 调度器。

    Returns:
        触发结果。
    """
    result = await scheduler.trigger_now(task_name)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
