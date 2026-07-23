"""响应体模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TokenResponse(BaseModel):
    """Token 响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserInfoResponse(BaseModel):
    """用户信息响应。"""

    id: str
    email: str
    display_name: str
    status: str
    created_at: str | None = None


class WorkspaceResponse(BaseModel):
    """工作空间响应。"""

    id: str
    organization_id: str
    name: str
    slug: str
    knowledge_scope: str
    is_archived: bool
    created_at: str | None = None


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    version: str = "0.1.0"
    connections: dict[str, Any] = {}
    gateway: str = "ready"
    model_config: dict[str, bool] = {}
