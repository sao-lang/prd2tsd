"""Auth 相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Token 响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15分钟


class TokenRefreshRequest(BaseModel):
    """Token 刷新请求。"""

    refresh_token: str


class LoginRequest(BaseModel):
    """登录请求。"""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求。"""

    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    password: str = Field(..., min_length=6)
    display_name: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    """用户信息响应。"""

    id: str
    email: str
    display_name: str
    status: str
    created_at: datetime | None = None


class TokenPayload(BaseModel):
    """JWT Payload。"""

    sub: str  # user_id
    org_id: str = ""
    ws_id: str = ""
    permissions: list[str] = Field(default_factory=list)
    exp: int = 0
