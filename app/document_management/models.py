"""文档管理 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel


class DocumentCreate(BaseModel):
    """创建文档记录请求（上传后由服务层填充）。"""

    original_filename: str
    file_size: int
    file_type: str
    mime_type: str | None = None
    file_hash: str | None = None
    storage_path: str = ""
    session_id: str | None = None
    task_id: str | None = None
    tags: list[str] | None = None


class DocumentUpdate(BaseModel):
    """更新文档请求。"""

    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    processing_status: str | None = None
    processing_error: str | None = None


class DocumentOut(BaseModel):
    """文档响应。"""

    id: str
    workspace_id: str
    user_id: str
    original_filename: str
    file_size: int
    file_type: str
    mime_type: str | None = None
    file_hash: str | None = None
    title: str | None = None
    description: str | None = None
    page_count: int | None = None
    word_count: int | None = None
    source_url: str | None = None
    processing_status: str = "pending"
    processing_error: str | None = None
    indexed_at: str | None = None
    entity_count: int = 0
    relation_count: int = 0
    tags: list[str] = []
    is_deleted: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class DocumentStats(BaseModel):
    """文档统计看板。"""

    total_documents: int = 0
    total_size_bytes: int = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}


class PreviewResult(BaseModel):
    """文档预览结果。"""

    document_id: str
    file_type: str
    text_preview: str | None = None
    page_count: int | None = None
    thumbnail_url: str | None = None
    error: str | None = None


class SearchResult(BaseModel):
    """文档搜索结果。"""

    document_id: str
    title: str
    description: str | None = None
    file_type: str
    file_size: int
    score: float = 0.0
    match_type: str = "fts"  # fts / semantic
    created_at: str | None = None


class UploadResponse(BaseModel):
    """上传响应。"""

    document: DocumentOut
    deduplicated: bool = False
