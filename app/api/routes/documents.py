"""文档管理 API 路由 — 上传/列表/预览/搜索/删除/统计。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.document import (
    CsvImportResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatsResponse,
    PreviewResponse,
    SearchResultItem,
    UploadResponse,
)
from app.auth.deps import get_current_user
from app.auth.middleware import _SCOPE_WS_ID as _SCOPE_WORKSPACE_ID
from app.core.logger import get_logger
from app.document_management.csv_loader import CsvDualPathIndexer
from app.document_management.service import DocumentManagementService, document_service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
logger = get_logger("prd2tsd.documents")


def _get_workspace_id(request: Request) -> str:
    """从请求上下文中获取工作空间 ID。

    Args:
        request: FastAPI 请求。

    Returns:
        工作空间 ID。

    Raises:
        HTTPException: 未找到工作空间上下文。
    """
    ws_id = request.scope.get(_SCOPE_WORKSPACE_ID)
    if not ws_id:
        raise HTTPException(status_code=400, detail="缺少工作空间上下文")
    return ws_id


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
) -> UploadResponse:
    """上传文档。

    Args:
        request: FastAPI 请求。
        file: 上传文件。
        user_id: 当前用户 ID。
        db: 数据库会话。
        svc: 文档管理服务。

    Returns:
        上传结果。
    """
    ws_id = _get_workspace_id(request)
    content = await file.read()

    try:
        result = await svc.upload(db, ws_id, user_id, content, file.filename or "unknown")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return UploadResponse(
        document=DocumentResponse(**result.document.model_dump()),
        deduplicated=result.deduplicated,
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    file_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    q: str | None = Query(default=None),
) -> DocumentListResponse:
    """列出或搜索文档。

    Args:
        request: FastAPI 请求。
        user_id: 当前用户 ID。
        db: 数据库会话。
        svc: 文档管理服务。
        page: 页码。
        page_size: 每页条数。
        file_type: 类型筛选。
        status: 状态筛选。
        sort_by: 排序字段。
        q: 搜索关键词。

    Returns:
        文档列表。
    """
    ws_id = _get_workspace_id(request)

    if q:
        results = await svc.search_documents(db, ws_id, q, page, page_size)
        return DocumentListResponse(
            items=[SearchResultItem(**r.model_dump()) for r in results],
            total=len(results),
            page=page,
            page_size=page_size,
            total_pages=1,
        )

    items, total = await svc.list_documents(db, ws_id, page, page_size, file_type, status, sort_by)
    return DocumentListResponse(
        items=[DocumentResponse(**d.model_dump()) for d in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/stats", response_model=DocumentStatsResponse)
async def get_document_stats(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
) -> DocumentStatsResponse:
    """获取文档统计。

    Args:
        request: FastAPI 请求。
        db: 数据库会话。
        svc: 文档管理服务。

    Returns:
        文档统计信息。
    """
    ws_id = _get_workspace_id(request)
    stats = await svc.get_stats(db, ws_id)
    return DocumentStatsResponse(
        **stats.model_dump(),
        total_size_mb=round(stats.total_size_bytes / (1024 * 1024), 2),
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
) -> DocumentResponse:
    """获取文档详情。

    Args:
        document_id: 文档 ID。
        db: 数据库会话。
        svc: 文档管理服务。

    Returns:
        文档信息。
    """
    doc = await svc.get_document(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return DocumentResponse(**doc.model_dump())


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
) -> None:
    """删除文档。

    Args:
        document_id: 文档 ID。
        db: 数据库会话。
        svc: 文档管理服务。
    """
    deleted = await svc.delete_document(db, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在")


@router.get("/{document_id}/preview", response_model=PreviewResponse)
async def preview_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
) -> PreviewResponse:
    """获取文档预览。

    Args:
        document_id: 文档 ID。
        db: 数据库会话。
        svc: 文档管理服务。

    Returns:
        预览内容。
    """
    preview = await svc.get_preview(db, document_id)
    if preview.error and "不存在" in preview.error:
        raise HTTPException(status_code=404, detail=preview.error)
    return PreviewResponse(**preview.model_dump())


@router.post("/{document_id}/reindex", status_code=200)
async def reindex_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
) -> dict:
    """重索引文档。

    Args:
        document_id: 文档 ID。
        db: 数据库会话。
        svc: 文档管理服务。

    Returns:
        操作结果。
    """
    success = await svc.reindex(db, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"status": "reindex_triggered", "document_id": document_id}


# ── CSV 导入专用端点 ──


@router.post("/csv-import", response_model=CsvImportResponse, status_code=201)
async def import_csv(
    request: Request,
    file: UploadFile,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    svc: DocumentManagementService = Depends(lambda: document_service),
) -> CsvImportResponse:
    """导入 CSV 文件（含双通路索引）。

    Args:
        request: FastAPI 请求。
        file: CSV 文件。
        user_id: 当前用户 ID。
        db: 数据库会话。
        svc: 文档管理服务。

    Returns:
        CSV 导入结果。
    """
    ws_id = _get_workspace_id(request)
    content = await file.read()
    filename = file.filename or "import.csv"

    try:
        result = await svc.upload(db, ws_id, user_id, content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # CSV 索引结果
    indexer = CsvDualPathIndexer()
    index_result = await indexer.process(content, filename, result.document.id)

    return CsvImportResponse(
        document_id=result.document.id,
        filename=filename,
        row_count=index_result["row_count"],
        column_count=index_result["column_count"],
        columns=index_result["column_profiles"],
        foreign_keys=index_result["foreign_keys"],
        text_unit_count=len(index_result["text_units"]),
    )
