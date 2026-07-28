"""SSE 流式推送 API 请求/响应体。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StreamGenerateRequest(BaseModel):
    """流式生成任务请求体。"""

    prd_content: str = Field(..., min_length=1, description="PRD 原始内容")
    prd_type: str = Field(default="md", pattern="^(md|pdf|docx|txt)$")
    workspace_id: str = Field(default="")
    stream: bool = Field(default=True, description="是否启用 SSE 流式推送")


class StreamQnARequest(BaseModel):
    """流式 Q&A 请求体。"""

    query: str = Field(..., min_length=1, description="用户问题")
    workspace_id: str = Field(default="")
    session_id: str | None = Field(default=None, description="关联会话 ID（可选）")


class StreamReviewRequest(BaseModel):
    """流式审核恢复请求体。"""

    decision: str = Field(..., pattern="^(approved|needs_changes)$", description="审核决策")
    comment: str = Field(default="", description="审核意见")
