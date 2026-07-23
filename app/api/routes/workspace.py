"""工作空间路由 — workspace CRUD + members。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.request import WorkspaceCreateRequest, WorkspaceUpdateRequest
from app.api.schemas.response import WorkspaceResponse
from app.auth.deps import get_current_user
from app.auth.middleware import _SCOPE_ORG_ID
from app.core.logger import get_logger
from app.models.role import Role
from app.models.team_member import TeamMember
from app.models.workspace import Workspace

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
logger = get_logger("prd2tsd.workspace")


def _to_workspace_response(ws: Workspace) -> WorkspaceResponse:
    """将 Workspace 模型转为响应对象。

    Args:
        ws: Workspace 模型实例。

    Returns:
        WorkspaceResponse。
    """
    return WorkspaceResponse(
        id=str(ws.id),
        organization_id=str(ws.organization_id),
        name=ws.name,
        slug=ws.slug,
        knowledge_scope=ws.knowledge_scope,
        is_archived=ws.is_archived,
        created_at=ws.created_at.isoformat() if ws.created_at else None,
    )


async def _get_workspace_or_404(
    workspace_id: str,
    db: AsyncSession,
) -> Workspace:
    """获取工作空间，不存在则抛 404。

    Args:
        workspace_id: 工作空间 ID。
        db: 数据库会话。

    Returns:
        Workspace 实例。

    Raises:
        HTTPException: 工作空间不存在。
    """
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    return ws


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    req: WorkspaceCreateRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """创建工作空间。

    Args:
        req: 创建请求。
        request: FastAPI 请求。
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        创建的工作空间信息。
    """
    org_id = request.scope.get(_SCOPE_ORG_ID, "")
    if not org_id:
        raise HTTPException(status_code=400, detail="请先加入一个组织")

    result = await db.execute(
        select(Workspace).where(
            Workspace.organization_id == org_id,
            Workspace.slug == req.slug,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该组织下已存在相同 slug 的工作空间")

    ws = Workspace(organization_id=org_id, name=req.name, slug=req.slug)
    db.add(ws)
    await db.flush()

    # 自动赋予 admin 角色
    result = await db.execute(
        select(Role).where(
            Role.organization_id == org_id, Role.name == "admin", Role.is_system,
        )
    )
    admin_role = result.scalar_one_or_none()
    if admin_role:
        db.add(TeamMember(workspace_id=ws.id, user_id=user_id, role_id=admin_role.id))

    await db.commit()
    await db.refresh(ws)
    logger.info("工作空间创建成功: %s (%s)", ws.name, ws.slug)
    return _to_workspace_response(ws)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[WorkspaceResponse]:
    """获取当前用户的工作空间列表。

    Args:
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        工作空间列表。
    """
    result = await db.execute(
        select(Workspace)
        .join(TeamMember, TeamMember.workspace_id == Workspace.id)
        .where(TeamMember.user_id == user_id, ~Workspace.is_archived)
    )
    workspaces = result.scalars().all()

    return [
        WorkspaceResponse(
            id=str(ws.id),
            organization_id=str(ws.organization_id),
            name=ws.name,
            slug=ws.slug,
            knowledge_scope=ws.knowledge_scope,
            is_archived=ws.is_archived,
            created_at=ws.created_at.isoformat() if ws.created_at else None,
        )
        for ws in workspaces
    ]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """获取工作空间详情。

    Args:
        workspace_id: 工作空间 ID。
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        工作空间详情。
    """
    ws = await _get_workspace_or_404(workspace_id, db)
    return _to_workspace_response(ws)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    req: WorkspaceUpdateRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    """更新工作空间。

    Args:
        workspace_id: 工作空间 ID。
        req: 更新请求。
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        更新后的工作空间信息。
    """
    ws = await _get_workspace_or_404(workspace_id, db)
    if req.name is not None:
        ws.name = req.name
    if req.slug is not None:
        ws.slug = req.slug
    if req.is_archived is not None:
        ws.is_archived = req.is_archived
    await db.commit()
    await db.refresh(ws)
    return _to_workspace_response(ws)


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """删除（归档）工作空间。

    Args:
        workspace_id: 工作空间 ID。
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        归档成功消息。
    """
    ws = await _get_workspace_or_404(workspace_id, db)
    ws.is_archived = True
    await db.commit()
    logger.info("工作空间已归档: %s", workspace_id)
    return {"message": "工作空间已归档"}



