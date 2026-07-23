"""Auth 路由 — login / refresh / logout / me。"""

from __future__ import annotations

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.request import LoginRequest, RefreshTokenRequest, RegisterRequest
from app.api.schemas.response import TokenResponse, UserInfoResponse
from app.auth.deps import get_current_user
from app.auth.token_manager import token_manager
from app.core.logger import get_logger
from app.models.organization import Organization
from app.models.role import Role
from app.models.team_member import TeamMember
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = get_logger("prd2tsd.auth.routes")


async def _create_user(db: AsyncSession, req: RegisterRequest) -> User:
    """创建用户。

    Args:
        db: 数据库会话。
        req: 注册请求。

    Returns:
        创建的用户。
    """
    hashed_pw = _bcrypt.hashpw(req.password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
    user = User(
        email=req.email, display_name=req.display_name,
        hashed_password=hashed_pw, auth_provider="jwt",
        auth_id=req.email, status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _create_default_org(db: AsyncSession, user: User) -> Organization:
    """创建默认组织。

    Args:
        db: 数据库会话。
        user: 用户对象。

    Returns:
        创建的组织。
    """
    org = Organization(
        name=f"{user.display_name}的组织",
        slug=f"org-{user.id[:8]}", plan="free",
    )
    db.add(org)
    await db.flush()
    return org


async def _create_personal_workspace(db: AsyncSession, org: Organization, user: User) -> Workspace:
    """创建个人工作空间。

    Args:
        db: 数据库会话。
        org: 组织对象。
        user: 用户对象。

    Returns:
        创建的工作空间。
    """
    ws = Workspace(
        organization_id=org.id,
        name=f"{user.display_name}的工作空间",
        slug=f"ws-{user.id[:8]}",
    )
    db.add(ws)
    await db.flush()
    return ws


async def _create_default_role(db: AsyncSession, org: Organization) -> Role:
    """创建默认 admin 角色。

    Args:
        db: 数据库会话。
        org: 组织对象。

    Returns:
        创建的角色。
    """
    permissions = [
        "workspace:create", "workspace:read", "workspace:update",
        "workspace:delete", "workspace:manage_members",
        "prd:create", "prd:read", "prd:update", "prd:delete",
        "model_config:read", "model_config:update",
    ]
    role = Role(organization_id=org.id, name="admin", is_system=True, permissions=permissions)
    db.add(role)
    await db.flush()
    return role


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """用户注册。

    Args:
        req: 注册请求（email, password, display_name）。
        db: 数据库会话。

    Returns:
        TokenResponse（access_token + refresh_token）。

    Raises:
        HTTPException: 邮箱已注册时抛出 409。
    """
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="邮箱已注册")

    user = await _create_user(db, req)
    org = await _create_default_org(db, user)
    ws = await _create_personal_workspace(db, org, user)
    admin_role = await _create_default_role(db, org)
    db.add(TeamMember(workspace_id=ws.id, user_id=user.id, role_id=admin_role.id))
    await db.commit()

    access_token = token_manager.create_access_token(
        user_id=str(user.id), org_id=str(org.id),
        ws_id=str(ws.id), permissions=admin_role.permissions,
    )
    refresh_token = token_manager.create_refresh_token(str(user.id))
    logger.info("用户注册成功: %s", req.email)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """用户登录。

    Args:
        req: 登录请求（email, password）。
        db: 数据库会话。

    Returns:
        TokenResponse（access_token + refresh_token）。

    Raises:
        HTTPException: 邮箱或密码错误时抛出 401。
    """
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not _bcrypt.checkpw(req.password.encode("utf-8"), user.hashed_password.encode("utf-8")):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if user.status != "active":
        raise HTTPException(status_code=403, detail="账号已被禁用")

    # 获取用户的工作空间和角色（取最新加入的）
    result = await db.execute(
        select(TeamMember)
        .where(TeamMember.user_id == user.id)
        .order_by(TeamMember.created_at.desc())
    )
    members = result.scalars().all()
    member = members[0] if members else None

    org_id = ""
    ws_id = ""
    permissions: list[str] = []

    if member:
        ws_id = str(member.workspace_id)
        # 获取组织和角色
        ws_result = await db.execute(
            select(Workspace).where(Workspace.id == member.workspace_id)
        )
        ws = ws_result.scalar_one_or_none()
        if ws:
            org_id = str(ws.organization_id)

        role_result = await db.execute(
            select(Role).where(Role.id == member.role_id)
        )
        role = role_result.scalar_one_or_none()
        if role:
            permissions = role.permissions

    access_token = token_manager.create_access_token(
        user_id=str(user.id),
        org_id=org_id,
        ws_id=ws_id,
        permissions=permissions,
    )
    refresh_token = token_manager.create_refresh_token(str(user.id))

    logger.info("用户登录成功: %s", req.email)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    req: RefreshTokenRequest,
) -> TokenResponse:
    """刷新 Access Token。

    Args:
        req: 刷新请求（refresh_token）。

    Returns:
        新的 TokenResponse。

    Raises:
        HTTPException: Refresh Token 无效时抛出 401。
    """
    new_access = token_manager.refresh_access_token(req.refresh_token)
    if not new_access:
        raise HTTPException(status_code=401, detail="Refresh Token 无效或已过期")

    return TokenResponse(
        access_token=new_access,
        refresh_token=req.refresh_token,
    )


@router.post("/logout")
async def logout() -> dict:
    """登出（客户端清除 Token）。

    Returns:
        登出成功消息。
    """
    return {"message": "登出成功"}


@router.get("/me", response_model=UserInfoResponse)
async def get_me(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserInfoResponse:
    """获取当前用户信息。

    Args:
        request: FastAPI 请求。
        user_id: 当前用户 ID。
        db: 数据库会话。

    Returns:
        用户信息。
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return UserInfoResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        status=user.status,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )
