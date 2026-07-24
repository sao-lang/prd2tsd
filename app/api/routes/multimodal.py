"""多模态检索 API 路由 — 以图搜图/文搜图/图文混合。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.api.schemas.multimodal import ImageIndexResponse, ImageSearchResult, SearchResultList
from app.auth.deps import get_current_user
from app.multimodal.multimodal_search import MultimodalSearchService

router = APIRouter(prefix="/api/v1/multimodal", tags=["multimodal"])


@router.post("/index", response_model=ImageIndexResponse, status_code=201)
async def index_image(
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    document_id: str = Form(...),
    page_number: int = Form(default=0),
    user_id: str = Depends(get_current_user),
) -> ImageIndexResponse:
    """索引一张图片。

    Args:
        file: 图片文件。
        caption: 图片说明。
        document_id: 所属文档 ID。
        page_number: 页码。
        user_id: 当前用户 ID。

    Returns:
        索引结果。
    """
    content = await file.read()
    svc = MultimodalSearchService()
    chunk = await svc.index_image(document_id, page_number, content, caption)
    return ImageIndexResponse(
        chunk_id=chunk.chunk_id,
        document_id=document_id,
        caption=caption,
    )


@router.post("/search-by-image", response_model=SearchResultList)
async def search_by_image(
    file: UploadFile = File(...),
    top_k: int = Query(default=10, ge=1, le=50),
    user_id: str = Depends(get_current_user),
) -> SearchResultList:
    """以图搜图。

    Args:
        file: 查询图片。
        top_k: 返回结果数。
        user_id: 当前用户 ID。

    Returns:
        搜索结果。
    """
    content = await file.read()
    svc = MultimodalSearchService()
    results = await svc.search_by_image(content, top_k)
    return SearchResultList(
        results=[ImageSearchResult(**r) for r in results],
        query_type="image",
    )


@router.get("/search-by-text", response_model=SearchResultList)
async def search_by_text(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=10, ge=1, le=50),
    user_id: str = Depends(get_current_user),
) -> SearchResultList:
    """文搜图。

    Args:
        q: 查询文本。
        top_k: 返回结果数。
        user_id: 当前用户 ID。

    Returns:
        搜索结果。
    """
    svc = MultimodalSearchService()
    results = await svc.search_by_text(q, top_k)
    return SearchResultList(
        results=[ImageSearchResult(**r) for r in results],
        query_type="text",
    )


@router.post("/hybrid-search", response_model=SearchResultList)
async def hybrid_search(
    file: UploadFile | None = File(default=None),
    q: str = Form(default=""),
    top_k: int = Query(default=10, ge=1, le=50),
    user_id: str = Depends(get_current_user),
) -> SearchResultList:
    """图文混合检索。

    Args:
        file: 图片（可选）。
        q: 文本（可选）。
        top_k: 返回结果数。
        user_id: 当前用户 ID。

    Returns:
        融合后的搜索结果。
    """
    image_bytes = await file.read() if file else None
    svc = MultimodalSearchService()
    results = await svc.hybrid_search(image_bytes, q or None, top_k)
    return SearchResultList(
        results=[ImageSearchResult(**r) for r in results],
        query_type="hybrid",
    )
