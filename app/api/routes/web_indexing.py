"""Web 索引 API 路由 — URL 抓取/爬虫/搜索回退。

E7 增强：抓取内容自动增量写入知识图谱。
E11 增强：搜索回退使用 LLM 生成关键词 + 结果实时索引。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.integration import (
    CrawlRequest,
    CrawlResult,
    SearchFallbackResult,
    WebFetchRequest,
    WebFetchResult,
)
from app.auth.deps import get_current_user
from app.auth.middleware import _SCOPE_WS_ID as _SCOPE_WORKSPACE_ID
from app.core.logger import get_logger
from app.knowledge_layer.pipeline import KnowledgeGraphBuilder
from app.knowledge_layer.vector_store import PGVectorStore
from app.llm_gateway import gateway as llm_gateway
from app.web_indexing.search_fallback import SearchFallback
from app.web_indexing.web_crawler import WebCrawler
from app.web_indexing.web_loader import WebLoader
from app.web_indexing.web_sync import WebSyncScheduler

router = APIRouter(prefix="/api/v1/web-indexing", tags=["web-indexing"])
logger = get_logger("prd2tsd.web_indexing")


def _get_workspace_id(request: Request) -> str:
    ws_id = request.scope.get(_SCOPE_WORKSPACE_ID)
    if not ws_id:
        raise HTTPException(status_code=400, detail="缺少工作空间上下文")
    return ws_id


@router.post("/fetch", response_model=WebFetchResult)
async def fetch_url(
    req: WebFetchRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
    index_to_kg: bool = Query(default=True, description="是否将抓取内容写入知识图谱"),
) -> WebFetchResult:
    """抓取单个 URL 并提取正文。

    E7 增强：抓取内容自动增量写入知识图谱（Neo4j + PGVector）。

    Args:
        req: 抓取请求。
        request: FastAPI 请求。
        user_id: 当前用户 ID。
        index_to_kg: 是否将抓取内容写入知识图谱。

    Returns:
        抓取结果。
    """
    loader = WebLoader()
    result = await loader.fetch(req.url)

    # E7 增强：抓取内容增量写入知识图谱
    if index_to_kg and result.get("text_content") and not result.get("error"):
        try:
            ws_id = _get_workspace_id(request)
            builder = KnowledgeGraphBuilder()
            stats = await builder.build_from_text(
                text=result["text_content"],
                source_name=result.get("title", "") or req.url,
                workspace_id=ws_id,
            )
            logger.info(
                "Web 内容已写入知识图谱: url=%s, entities=%d, chunks=%d",
                req.url, stats.entities, stats.chunks,
            )
            result["kg_build_stats"] = {
                "entities": stats.entities,
                "chunks": stats.chunks,
            }
        except Exception as exc:
            logger.warning("Web 内容写入知识图谱失败（不影响返回）: %s", exc)

    return WebFetchResult(
        url=result["url"],
        title=result["title"],
        content=result["content"],
        error=result["error"],
    )


@router.post("/crawl", response_model=list[CrawlResult])
async def crawl_url(
    req: CrawlRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
    index_to_kg: bool = Query(default=True, description="是否将爬取内容写入知识图谱"),
) -> list[CrawlResult]:
    """递归爬取同域 URL。

    E7 增强：爬取结果自动增量写入知识图谱。

    Args:
        req: 爬取请求。
        request: FastAPI 请求。
        user_id: 当前用户 ID。
        index_to_kg: 是否将爬取内容写入知识图谱。

    Returns:
        爬取结果列表。
    """
    crawler = WebCrawler(max_pages=req.max_pages)
    results = await crawler.crawl(req.url)

    # E7 增强：爬取结果写入知识图谱
    if index_to_kg:
        try:
            ws_id = _get_workspace_id(request)
            builder = KnowledgeGraphBuilder()
            for r in results:
                if r.get("text_content") and not r.get("error"):
                    await builder.build_from_text(
                        text=r["text_content"],
                        source_name=r.get("title", "") or r["url"],
                        workspace_id=ws_id,
                    )
            logger.info(
                "爬取结果已写入知识图谱: start_url=%s, pages=%d",
                req.url, len(results),
            )
        except Exception as exc:
            logger.warning("爬取结果写入知识图谱失败（不影响返回）: %s", exc)

    return [
        CrawlResult(
            url=r["url"],
            title=r["title"],
            content=r["content"],
            error=r["error"],
        )
        for r in results
    ]


@router.post("/sync", response_model=WebFetchResult)
async def sync_url(
    req: WebFetchRequest,
    force: bool = Query(default=False),
    user_id: str = Depends(get_current_user),
) -> WebFetchResult:
    """定时同步 URL（ETag/Last-Modified 变更检测）。

    Args:
        req: 同步请求。
        force: 是否强制重新抓取。
        user_id: 当前用户 ID。

    Returns:
        同步结果。
    """
    scheduler = WebSyncScheduler()
    result = await scheduler.sync(req.url, force=force)
    return WebFetchResult(
        url=result["url"],
        content=result.get("content", ""),
        error=result.get("error"),
    )


@router.post("/search-fallback", response_model=SearchFallbackResult)
async def search_fallback(
    request: Request,
    q: str = Query(..., min_length=1, description="搜索查询"),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    index_results: bool = Query(default=True, description="是否将搜索结果索引到向量库"),
) -> SearchFallbackResult:
    """搜索引擎回退 — 当本地检索不足时自动触发网络搜索。

    E11 增强：使用 LLM 生成优化关键词 + 搜索结果实时索引到 PGVector。

    Args:
        request: FastAPI 请求。
        q: 搜索关键词。
        user_id: 当前用户 ID。
        db: 数据库会话。
        index_results: 是否将搜索结果索引到向量库。

    Returns:
        搜索结果（含回退标记）。
    """
    ws_id = _get_workspace_id(request)
    vector_store = PGVectorStore(session=db) if index_results else None

    # E11 增强：传入 LLM Gateway 用于关键词生成
    fallback = SearchFallback(llm_gateway=llm_gateway)

    # 使用 search_and_index 实现结果实时索引
    results = await fallback.search_and_index(
        query=q,
        workspace_id=ws_id,
        max_results=5,
        vector_store=vector_store,
    )

    return SearchFallbackResult(
        query=q,
        fallback_triggered=True,
        results=results,
    )
