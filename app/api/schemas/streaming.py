"""SSE 流式推送 API 请求/响应体。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StreamReviewRequest(BaseModel):
    """流式审核恢复请求体。"""

    decision: str = Field(..., pattern="^(approved|needs_changes)$", description="审核决策")
    comment: str = Field(default="", description="审核意见")
