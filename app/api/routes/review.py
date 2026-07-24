"""人工审核路由 — GET /api/v1/review/pending + POST /api/v1/review/{task_id}/{stage}。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user
from app.models.user import User
from app.orchestrator.state import TaskInfo
from app.task_manager import task_manager

router = APIRouter(prefix="/api/v1/review", tags=["review"])


class ReviewRequest(BaseModel):
    """审核请求体。"""

    decision: str = Field(default="approved", pattern="^(approved|needs_changes)$")
    comment: str = Field(default="")


class ReviewPendingResponse(BaseModel):
    """待审核列表响应。"""

    tasks: list[TaskInfo]
    total: int


@router.get("/pending", response_model=ReviewPendingResponse)
async def get_pending_reviews(
    current_user: User = Depends(get_current_user),
) -> ReviewPendingResponse:
    """获取所有待人工审核的任务。"""
    pending = await task_manager.get_pending_reviews()
    return ReviewPendingResponse(tasks=pending, total=len(pending))


@router.post("/{task_id}/{stage}")
async def submit_review(
    task_id: str,
    stage: str,
    req: ReviewRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """提交审核结果。

    Args:
        task_id: 任务 ID。
        stage: 审核阶段（analysis / planning）。
        req: 审核请求体。

    Returns:
        处理结果。
    """
    if stage not in ("analysis", "planning"):
        raise HTTPException(status_code=400, detail="无效的审核阶段")

    success = await task_manager.resolve_review(
        task_id=task_id,
        stage=stage,
        decision=req.decision,
        comment=req.comment,
    )
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或不在审核状态")

    return {"status": "ok", "message": "审核已提交"}
