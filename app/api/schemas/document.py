"""文档管理 API 请求/响应体。"""

from __future__ import annotations

from pydantic import BaseModel


class DocumentResponse(BaseModel):
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
    processing_status: str = "pending"
    processing_error: str | None = None
    indexed_at: str | None = None
    entity_count: int = 0
    tags: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None


class DocumentListResponse(BaseModel):
    """文档列表响应。"""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentStatsResponse(BaseModel):
    """文档统计响应。"""

    total_documents: int = 0
    total_size_bytes: int = 0
    total_size_mb: float = 0.0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}


class UploadResponse(BaseModel):
    """上传响应。"""

    document: DocumentResponse
    deduplicated: bool = False


class PreviewResponse(BaseModel):
    """预览响应。"""

    document_id: str
    file_type: str
    text_preview: str | None = None
    page_count: int | None = None
    error: str | None = None


class SearchResultItem(BaseModel):
    """搜索结果项。"""

    document_id: str
    title: str
    description: str | None = None
    file_type: str
    file_size: int
    score: float = 0.0
    match_type: str = "fts"
    created_at: str | None = None


class CsvImportResponse(BaseModel):
    """CSV 导入响应。"""

    document_id: str
    filename: str
    row_count: int = 0
    column_count: int = 0
    columns: list[dict] = []
    foreign_keys: list[str] = []
    text_unit_count: int = 0
