"""协作文档 API 请求/响应体。"""

from pydantic import BaseModel, Field


class CommentCreateRequest(BaseModel):
    """创建评论请求。"""

    document_id: str
    content: str = Field(..., min_length=1)
    selection_text: str = ""
    selection_start: int = 0
    selection_end: int = 0
    parent_comment_id: str | None = None


class CommentResponse(BaseModel):
    """评论响应。"""

    id: str
    document_id: str
    user_id: str
    content: str
    selection_text: str = ""
    selection_start: int = 0
    selection_end: int = 0
    parent_comment_id: str | None = None
    resolved: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class SuggestionCreateRequest(BaseModel):
    """创建建议请求。"""

    document_id: str
    original_text: str = Field(..., description="原文")
    suggested_text: str = Field(..., description="建议修改")
    reason: str = ""


class SuggestionResponse(BaseModel):
    """建议响应。"""

    id: str
    document_id: str
    user_id: str
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
    action: str
    detail: str = ""
    version: int = 1
    created_at: str | None = None
