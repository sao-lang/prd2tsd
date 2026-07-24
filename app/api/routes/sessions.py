"""会话历史 API 路由 — 会话 CRUD + 消息管理 + 搜索 + 导出。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.session import (
    ExportResponse,
    MessageCreateRequest,
    MessageResponse,
    PageResultResponse,
    SearchResultItem,
    SessionCreateRequest,
    SessionResponse,
    SessionUpdateRequest,
)
from app.auth.deps import get_current_user
from app.auth.middleware import _SCOPE_WS_ID as _SCOPE_WORKSPACE_ID
from app.core.logger import get_logger
from app.session_history.models import MessageCreate, SessionCreate, SessionUpdate
from app.session_history.service import SessionHistoryService, session_service

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])
logger = get_logger("prd2tsd.sessions")


def _get_workspace_id(request: Request) -> str:
    """从请求上下文中获取工作空间 ID。

    Args:
        request: FastAPI 请求。

    Returns:
        工作空间 ID。

    Raises:
        HTTPException: 未找到工作空间上下文。
    """
    ws_id = request.scope.get(_SCOPE_WORKSPACE_ID)
    if not ws_id:
        raise HTTPException(status_code=400, detail="缺少工作空间上下文")
    return ws_id


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    req: SessionCreateRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
) -> SessionResponse:
    """创建新会话。

    Args:
        req: 创建请求。
        request: FastAPI 请求。
        user_id: 当前用户 ID。
        db: 数据库会话。
        svc: 会话历史服务。

    Returns:
        创建的会话信息。
    """
    ws_id = _get_workspace_id(request)
    data = SessionCreate(
        title=req.title,
        session_type=req.session_type,
        source_prd_id=req.source_prd_id,
        tags=req.tags,
    )
    session = await svc.create_session(db, ws_id, user_id, data)
    return SessionResponse(**session.model_dump())


@router.get("", response_model=PageResultResponse)
async def list_sessions(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    session_type: str | None = Query(default=None),
    sort_by: str = Query(default="last_message_at"),
    q: str | None = Query(default=None, description="搜索关键词"),
) -> PageResultResponse:
    """列出会话（分页+筛选+搜索）。

    Args:
        request: FastAPI 请求。
        user_id: 当前用户 ID。
        db: 数据库会话。
        svc: 会话历史服务。
        page: 页码。
        page_size: 每页条数。
        status: 状态筛选。
        session_type: 类型筛选。
        sort_by: 排序字段。
        q: 搜索关键词。

    Returns:
        分页结果。
    """
    ws_id = _get_workspace_id(request)

    if q:
        results = await svc.search_sessions(db, ws_id, q, page, page_size)
        return PageResultResponse(
            items=[r.model_dump() for r in results],
            total=len(results),
            page=page,
            page_size=page_size,
            total_pages=1,
        )

    result = await svc.list_sessions(
        db, ws_id, page, page_size, status, session_type, sort_by,
    )
    return PageResultResponse(
        items=[SessionResponse(**s.model_dump()) for s in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
) -> SessionResponse:
    """获取单个会话详情。

    Args:
        session_id: 会话 ID。
        db: 数据库会话。
        svc: 会话历史服务。

    Returns:
        会话信息。
    """
    session = await svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionResponse(**session.model_dump())


@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    req: SessionUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
) -> SessionResponse:
    """更新会话。

    Args:
        session_id: 会话 ID。
        req: 更新请求。
        db: 数据库会话。
        svc: 会话历史服务。

    Returns:
        更新后的会话。
    """
    data = SessionUpdate(**req.model_dump(exclude_none=True))
    session = await svc.update_session(db, session_id, data)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionResponse(**session.model_dump())


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
) -> None:
    """软删除会话。

    Args:
        session_id: 会话 ID。
        db: 数据库会话。
        svc: 会话历史服务。
    """
    deleted = await svc.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")


# ── 消息管理 ──


@router.post("/{session_id}/messages", response_model=MessageResponse, status_code=201)
async def add_message(
    session_id: str,
    req: MessageCreateRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
) -> MessageResponse:
    """添加消息到会话。

    Args:
        session_id: 会话 ID。
        req: 消息内容。
        user_id: 当前用户 ID。
        db: 数据库会话。
        svc: 会话历史服务。

    Returns:
        创建的消息。
    """
    data = MessageCreate(
        role=req.role,
        content=req.content,
        content_type=req.content_type,
        parent_message_id=req.parent_message_id,
        attachments=req.attachments,
    )
    msg = await svc.add_message(db, session_id, user_id, data)
    return MessageResponse(**msg.model_dump())


@router.get("/{session_id}/messages", response_model=PageResultResponse)
async def get_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PageResultResponse:
    """获取会话的消息列表。

    Args:
        session_id: 会话 ID。
        db: 数据库会话。
        svc: 会话历史服务。
        page: 页码。
        page_size: 每页条数。

    Returns:
        分页消息列表。
    """
    result = await svc.get_messages(db, session_id, page, page_size)
    return PageResultResponse(
        items=[MessageResponse(**m.model_dump()) for m in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


# ── 搜索 ──


@router.get("/search/messages", response_model=list[SearchResultItem])
async def search_messages(
    request: Request,
    q: str = Query(..., min_length=1, description="搜索关键词"),
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[SearchResultItem]:
    """全文搜索消息内容。

    Args:
        request: FastAPI 请求。
        q: 搜索关键词。
        db: 数据库会话。
        svc: 会话历史服务。
        page: 页码。
        page_size: 每页条数。

    Returns:
        搜索结果列表。
    """
    ws_id = _get_workspace_id(request)
    results = await svc.search_messages(db, ws_id, q, page, page_size)
    return [SearchResultItem(**r.model_dump()) for r in results]


# ── 导出 ──


@router.get("/{session_id}/export", response_model=ExportResponse)
async def export_session(
    session_id: str,
    fmt: str = Query(default="markdown", pattern="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
) -> ExportResponse:
    """导出会话。

    Args:
        session_id: 会话 ID。
        fmt: 导出格式（markdown / json）。
        db: 数据库会话。
        svc: 会话历史服务。

    Returns:
        导出内容。
    """
    try:
        content = await svc.export_session(db, session_id, fmt)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    ext = "md" if fmt == "markdown" else "json"
    session = await svc.get_session(db, session_id)
    filename = f"session-{session_id[:8]}.{ext}" if session else f"session-{session_id[:8]}.{ext}"

    return ExportResponse(content=content, format=fmt, filename=filename)


# ── 老化清理 ──


@router.post("/cleanup", status_code=200)
async def cleanup_sessions(
    request: Request,
    plan: str = Query(default="free", pattern="^(free|pro|enterprise)$"),
    db: AsyncSession = Depends(get_db_session),
    svc: SessionHistoryService = Depends(lambda: session_service),
) -> dict:
    """执行会话老化清理。

    Args:
        request: FastAPI 请求。
        plan: 套餐类型。
        db: 数据库会话。
        svc: 会话历史服务。

    Returns:
        清理结果。
    """
    ws_id = _get_workspace_id(request)
    deleted = await svc.cleanup_expired(db, ws_id, plan)
    return {"deleted": deleted, "plan": plan}
