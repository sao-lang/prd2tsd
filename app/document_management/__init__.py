"""文档管理模块 — 上传/去重/预览/搜索/CSV 双通路索引。"""

from app.document_management.csv_loader import CsvDualPathIndexer
from app.document_management.deduplication import DocumentDeduplicator
from app.document_management.models import (
    DocumentCreate,
    DocumentOut,
    DocumentStats,
    DocumentUpdate,
)
from app.document_management.preview import DocumentPreviewGenerator
from app.document_management.repository import DocumentRepository
from app.document_management.search import DocumentSearchService
from app.document_management.service import DocumentManagementService
from app.document_management.storage import DocumentStorage

__all__ = [
    "DocumentCreate",
    "DocumentOut",
    "DocumentUpdate",
    "DocumentStats",
    "DocumentRepository",
    "DocumentStorage",
    "DocumentDeduplicator",
    "DocumentPreviewGenerator",
    "DocumentSearchService",
    "DocumentManagementService",
    "CsvDualPathIndexer",
]
