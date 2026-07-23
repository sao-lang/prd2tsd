"""API Schemas。"""

from app.api.schemas.request import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
)
from app.api.schemas.response import (
    HealthResponse,
    TokenResponse,
    UserInfoResponse,
    WorkspaceResponse,
)

__all__ = [
    "LoginRequest",
    "RegisterRequest",
    "RefreshTokenRequest",
    "WorkspaceCreateRequest",
    "WorkspaceUpdateRequest",
    "TokenResponse",
    "UserInfoResponse",
    "WorkspaceResponse",
    "HealthResponse",
]
