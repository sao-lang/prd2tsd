"""协作文档 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    """创建评论请求。"""

    document_id: str
    content: str = Field(..., min_length=1)
    selection_text: str = Field(default="", description="选中的段落文本")
    selection_start: int = Field(default=0, description="选中位置起始")
    selection_end: int = Field(default=0, description="选中位置结束")
    parent_comment_id: str | None = None


class CommentOut(BaseModel):
    """评论响应。"""

    id: str
    document_id: str
    user_id: str
    user_name: str = ""
    content: str
    selection_text: str = ""
    selection_start: int = 0
    selection_end: int = 0
    parent_comment_id: str | None = None
    resolved: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class SuggestionCreate(BaseModel):
    """创建建议请求。"""

    document_id: str
    original_text: str = Field(..., description="原文")
    suggested_text: str = Field(..., description="建议修改")
    reason: str = Field(default="", description="修改理由")


class SuggestionOut(BaseModel):
    """建议响应。"""

    id: str
    document_id: str
    user_id: str
    user_name: str = ""
    original_text: str
    suggested_text: str
    reason: str = ""
    status: str = "pending"
    created_at: str | None = None
    updated_at: str | None = None


class ChangeLogEntry(BaseModel):
    """变更历史条目。"""

    id: str
    document_id: str
    user_id: str
    user_name: str = ""
    action: str  # created / updated / comment_added / suggestion_applied / deleted
    detail: str = ""
    version: int = 1
    created_at: str | None = None
