"""FastAPI 中间件 — 提取用户和租户上下文。"""

from __future__ import annotations

from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.token_manager import token_manager
from app.core.logger import get_logger

logger = get_logger("prd2tsd.auth.middleware")

# scope keys 用于跨中间件传递上下文
_SCOPE_USER_ID = "auth.user_id"
_SCOPE_ORG_ID = "auth.org_id"
_SCOPE_WS_ID = "auth.ws_id"
_SCOPE_PERMISSIONS = "auth.permissions"


def _init_scope(scope: dict) -> None:
    """初始化 scope 中的认证上下文。

    Args:
        scope: ASGI scope 字典。
    """
    scope.setdefault(_SCOPE_USER_ID, "")
    scope.setdefault(_SCOPE_ORG_ID, "")
    scope.setdefault(_SCOPE_WS_ID, "")
    scope.setdefault(_SCOPE_PERMISSIONS, [])


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件。

    从请求头中提取 JWT Token，解析并设置用户上下文到 request.scope。
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """处理请求。

        Args:
            request: FastAPI 请求对象。
            call_next: 下一个处理函数。

        Returns:
            Response。
        """
        _init_scope(request.scope)

        # 从 Authorization 头中提取 Token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = token_manager.verify_token(token)
            if payload:
                request.scope[_SCOPE_USER_ID] = payload.get("sub", "")
                request.scope[_SCOPE_ORG_ID] = payload.get("org_id", "")
                request.scope[_SCOPE_WS_ID] = payload.get("ws_id", "")
                request.scope[_SCOPE_PERMISSIONS] = payload.get("permissions", [])

        response = await call_next(request)
        return response


class WorkspaceContextMiddleware(BaseHTTPMiddleware):
    """工作空间上下文中间件。

    从请求头或查询参数中提取当前工作空间 ID，设置到 request.scope。
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """处理请求。

        Args:
            request: FastAPI 请求对象。
            call_next: 下一个处理函数。

        Returns:
            Response。
        """
        _init_scope(request.scope)

        # 如果尚未设置 ws_id，尝试从请求中提取
        if not request.scope.get(_SCOPE_WS_ID):
            ws_id = request.headers.get("X-Workspace-ID", "")
            if not ws_id:
                ws_id = request.query_params.get("ws_id", "")
            request.scope[_SCOPE_WS_ID] = ws_id

        response = await call_next(request)
        return response
