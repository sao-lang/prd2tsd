"""会话历史 API 请求/响应体。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    """创建会话请求。"""

    title: str = Field(..., min_length=1, max_length=255)
    session_type: str = Field(default="generate")
    source_prd_id: str | None = None
    tags: list[str] | None = None


class SessionUpdateRequest(BaseModel):
    """更新会话请求。"""

    title: str | None = None
    session_type: str | None = None
    status: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)


class SessionResponse(BaseModel):
    """会话响应。"""

    id: str
    workspace_id: str
    user_id: str
    title: str
    session_type: str
    status: str
    summary: str | None = None
    message_count: int = 0
    token_count: int = 0
    cost_usd: float = 0.0
    rating: int | None = None
    tags: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None
    last_message_at: str | None = None


class MessageCreateRequest(BaseModel):
    """创建消息请求。"""

    role: str = Field(..., pattern="^(user|assistant|system|tool)$")
    content: str = Field(..., min_length=1)
    content_type: str = Field(default="text")
    parent_message_id: str | None = None
    attachments: list[dict[str, Any]] | None = None


class MessageResponse(BaseModel):
    """消息响应。"""

    id: str
    session_id: str
    role: str
    content: str
    content_type: str = "text"
    attachments: list[dict[str, Any]] = []
    turn_index: int
    token_count: int = 0
    cost_usd: float = 0.0
    latency_ms: int | None = None
    model_used: str | None = None
    created_at: str | None = None


class PageResultResponse(BaseModel):
    """分页结果响应。"""

    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class SearchResultItem(BaseModel):
    """搜索结果项。"""

    session_id: str
    message_id: str
    session_title: str
    content: str
    role: str
    turn_index: int
    score: float = 0.0
    created_at: str | None = None


class ExportResponse(BaseModel):
    """导出响应。"""

    content: str
    format: str
    filename: str
