"""Auth 依赖注入 — get_current_user, require_permission。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.auth.middleware import _SCOPE_ORG_ID, _SCOPE_USER_ID, _SCOPE_WS_ID, _SCOPE_PERMISSIONS
from app.auth.permissions import permission_checker
from app.core.exceptions import AuthenticationError, PermissionDeniedError


async def get_current_user(request: Request) -> str:
    """获取当前登录用户 ID。

    Args:
        request: FastAPI 请求对象。

    Returns:
        当前用户 ID。

    Raises:
        HTTPException: 未认证时抛出 401。
    """
    user_id = request.scope.get(_SCOPE_USER_ID, "")
    if not user_id:
        raise AuthenticationError("请先登录")
    return user_id


async def get_current_workspace(request: Request) -> str:
    """获取当前工作空间 ID。

    Args:
        request: FastAPI 请求对象。

    Returns:
        当前工作空间 ID。

    Raises:
        HTTPException: 未指定工作空间时抛出 400。
    """
    ws_id = request.scope.get(_SCOPE_WS_ID, "")
    if not ws_id:
        raise HTTPException(status_code=400, detail="请指定工作空间")
    return ws_id


def require_permission(permission: str):
    """依赖注入工厂 — 检查用户是否拥有指定权限。

    Args:
        permission: 所需权限名。

    Returns:
        依赖注入函数。
    """
    async def _check(request: Request) -> None:
        user_permissions = request.scope.get(_SCOPE_PERMISSIONS, [])
        if not permission_checker.check_permission(permission, user_permissions):
            raise PermissionDeniedError(f"缺少权限: {permission}")

    return _check


async def get_user_context(request: Request) -> dict:
    """获取当前用户的完整上下文信息。

    Args:
        request: FastAPI 请求对象。

    Returns:
        用户上下文字典。
    """
    return {
        "user_id": request.scope.get(_SCOPE_USER_ID, ""),
        "org_id": request.scope.get(_SCOPE_ORG_ID, ""),
        "ws_id": request.scope.get(_SCOPE_WS_ID, ""),
        "permissions": request.scope.get(_SCOPE_PERMISSIONS, []),
    }
