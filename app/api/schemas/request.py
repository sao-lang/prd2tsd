"""请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求。"""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求。"""

    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    password: str = Field(..., min_length=6)
    display_name: str = Field(..., min_length=1, max_length=128)


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求。"""

    refresh_token: str


class WorkspaceCreateRequest(BaseModel):
    """创建工作空间请求。"""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")


class WorkspaceUpdateRequest(BaseModel):
    """更新工作空间请求。"""

    name: str | None = Field(None, max_length=255)
    slug: str | None = Field(None, max_length=64, pattern=r"^[a-z0-9-]+$")
    is_archived: bool | None = None


class MemberAddRequest(BaseModel):
    """添加成员请求。"""

    user_id: str
    role_name: str = "viewer"
