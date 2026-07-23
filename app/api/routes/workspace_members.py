"""工作空间成员管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.request import MemberAddRequest
from app.auth.deps import get_current_user
from app.core.logger import get_logger
from app.models.role import Role
from app.models.team_member import TeamMember
from app.models.user import User

logger = get_logger("prd2tsd.workspace")

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/members", tags=["workspaces"])


async def _get_workspace_or_404(workspace_id: str, db: AsyncSession):
    """获取工作空间，不存在则抛 404。"""
    from app.models.workspace import Workspace
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    return ws


@router.post("")
async def add_member(
    workspace_id: str,
    req: MemberAddRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """添加团队成员。

    Args:
        workspace_id: 工作空间 ID。
        req: 添加成员请求。
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        添加成功消息。
    """
    ws = await _get_workspace_or_404(workspace_id, db)

    result = await db.execute(select(User).where(User.id == req.user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="用户不存在")

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.workspace_id == workspace_id,
            TeamMember.user_id == req.user_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该用户已是团队成员")

    result = await db.execute(
        select(Role).where(
            Role.organization_id == ws.organization_id,
            Role.name == req.role_name,
        )
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail=f"角色不存在: {req.role_name}")

    db.add(TeamMember(workspace_id=workspace_id, user_id=req.user_id, role_id=role.id))
    await db.commit()
    logger.info("成员已添加到工作空间: user=%s, ws=%s", req.user_id, workspace_id)
    return {"message": "成员添加成功"}


@router.delete("/{member_user_id}")
async def remove_member(
    workspace_id: str,
    member_user_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """移除团队成员。

    Args:
        workspace_id: 工作空间 ID。
        member_user_id: 成员用户 ID。
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        移除成功消息。
    """
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.workspace_id == workspace_id,
            TeamMember.user_id == member_user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="团队成员不存在")

    await db.delete(member)
    await db.commit()
    logger.info("成员已从工作空间移除: user=%s, ws=%s", member_user_id, workspace_id)
    return {"message": "成员已移除"}
