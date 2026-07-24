"""协作文档 API 路由 — 评论/建议/变更历史。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas.collaboration import (
    ChangeLogEntry,
    CommentCreateRequest,
    CommentResponse,
    SuggestionCreateRequest,
    SuggestionResponse,
)
from app.auth.deps import get_current_user
from app.collaboration.models import CommentCreate, SuggestionCreate
from app.collaboration.service import CollaborationService, collaboration_service

router = APIRouter(prefix="/api/v1/collaboration", tags=["collaboration"])


# ── 评论 ──


@router.post("/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    req: CommentCreateRequest,
    user_id: str = Depends(get_current_user),
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> CommentResponse:
    """添加评论。

    Args:
        req: 评论内容。
        user_id: 当前用户 ID。
        svc: 协作文档服务。

    Returns:
        创建的评论。
    """
    data = CommentCreate(**req.model_dump())
    result = await svc.add_comment(req.document_id, user_id, data)
    return CommentResponse(**result.model_dump())


@router.get("/comments", response_model=list[CommentResponse])
async def list_comments(
    document_id: str = Query(..., description="文档 ID"),
    include_resolved: bool = Query(default=False),
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> list[CommentResponse]:
    """获取文档评论。

    Args:
        document_id: 文档 ID。
        include_resolved: 是否包含已解决。
        svc: 协作文档服务。

    Returns:
        评论列表。
    """
    results = await svc.get_comments(document_id, include_resolved)
    return [CommentResponse(**r.model_dump()) for r in results]


@router.post("/comments/{comment_id}/resolve", response_model=dict)
async def resolve_comment(
    comment_id: str,
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> dict:
    """标记评论为已解决。

    Args:
        comment_id: 评论 ID。
        svc: 协作文档服务。

    Returns:
        操作结果。
    """
    success = await svc.resolve_comment(comment_id)
    if not success:
        raise HTTPException(status_code=404, detail="评论不存在")
    return {"status": "resolved"}


# ── 建议 ──


@router.post("/suggestions", response_model=SuggestionResponse, status_code=201)
async def create_suggestion(
    req: SuggestionCreateRequest,
    user_id: str = Depends(get_current_user),
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> SuggestionResponse:
    """创建建议修改。

    Args:
        req: 建议内容。
        user_id: 当前用户 ID。
        svc: 协作文档服务。

    Returns:
        创建的建议。
    """
    data = SuggestionCreate(**req.model_dump())
    result = await svc.create_suggestion(req.document_id, user_id, data)
    return SuggestionResponse(**result.model_dump())


@router.get("/suggestions", response_model=list[SuggestionResponse])
async def list_suggestions(
    document_id: str = Query(...),
    status: str | None = Query(default=None),
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> list[SuggestionResponse]:
    """获取文档建议。

    Args:
        document_id: 文档 ID。
        status: 状态筛选。
        svc: 协作文档服务。

    Returns:
        建议列表。
    """
    results = await svc.get_suggestions(document_id, status)
    return [SuggestionResponse(**r.model_dump()) for r in results]


@router.post("/suggestions/{suggestion_id}/approve", response_model=SuggestionResponse)
async def approve_suggestion(
    suggestion_id: str,
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> SuggestionResponse:
    """审批通过建议。

    Args:
        suggestion_id: 建议 ID。
        svc: 协作文档服务。

    Returns:
        更新后的建议。
    """
    result = await svc.approve_suggestion(suggestion_id)
    if not result:
        raise HTTPException(status_code=404, detail="建议不存在")
    return SuggestionResponse(**result.model_dump())


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionResponse)
async def reject_suggestion(
    suggestion_id: str,
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> SuggestionResponse:
    """拒绝建议。

    Args:
        suggestion_id: 建议 ID。
        svc: 协作文档服务。

    Returns:
        更新后的建议。
    """
    result = await svc.reject_suggestion(suggestion_id)
    if not result:
        raise HTTPException(status_code=404, detail="建议不存在")
    return SuggestionResponse(**result.model_dump())


# ── 变更历史 ──


@router.get("/history", response_model=list[ChangeLogEntry])
async def get_history(
    document_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    svc: CollaborationService = Depends(lambda: collaboration_service),
) -> list[ChangeLogEntry]:
    """获取文档变更历史。

    Args:
        document_id: 文档 ID。
        limit: 返回条数。
        svc: 协作文档服务。

    Returns:
        变更历史列表。
    """
    return await svc.get_history(document_id, limit)
