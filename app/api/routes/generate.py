"""生成路由 — POST /api/v1/generate + GET /api/v1/tasks/{task_id}。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_orchestrator
from app.auth.deps import get_current_user
from app.models.user import User
from app.orchestrator.state import TaskInfo
from app.task_manager import task_manager

router = APIRouter(prefix="/api/v1", tags=["generate"])


class GenerateRequest(BaseModel):
    """生成任务请求体。"""

    prd_content: str = Field(..., min_length=1, description="PRD 原始内容")
    prd_type: str = Field(default="md", pattern="^(md|pdf|docx|txt)$")
    workspace_id: str = Field(default="")


class GenerateResponse(BaseModel):
    """生成任务响应。"""

    task_id: str
    status: str = "running"


@router.post("/generate", response_model=GenerateResponse)
async def create_generation_task(
    req: GenerateRequest,
    current_user: User = Depends(get_current_user),
    orchestrator=Depends(get_orchestrator),
) -> GenerateResponse:
    """提交 PRD 生成任务。

    异步执行全链路分析→规划→生成→评测。
    """
    task_id = await task_manager.create_task(
        prd_raw=req.prd_content,
        prd_file_type=req.prd_type,
        workspace_id=req.workspace_id,
        user_id=str(current_user.id),
        user_role=current_user.role.name if hasattr(current_user, "role") else "",
        orchestrator=orchestrator,
    )
    return GenerateResponse(task_id=task_id)


@router.get("/tasks/{task_id}", response_model=TaskInfo)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> TaskInfo:
    """查询任务状态和结果。"""
    task = await task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
