"""搜索引擎回退 — 本地知识图谱检索不足时自动触发网络搜索（E11）。

E11 增强：
- LLM 生成搜索关键词（而非直接使用原始 query）
- 搜索结果实时索引到 PGVector
- 自动触发回退判断
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.core.logger import get_logger
from app.knowledge_layer.ingestion.entity_embedder import EntityEmbedder
from app.knowledge_layer.models import Chunk

logger = get_logger("prd2tsd.search_fallback")

# 简单搜索引擎 URL 模板（不使用专用 API Key）
_SEARCH_URLS = [
    "https://html.duckduckgo.com/html/?q={query}",
]


class SearchFallback:
    """搜索引擎回退。

    当本地知识图谱检索结果不足时，自动触发网络搜索并返回结果。
    E11 增强：LLM 关键词生成 + 结果实时索引。
    """

    MIN_RESULTS = 3  # 本地结果少于该值时触发回退

    def __init__(self, llm_gateway: Any | None = None) -> None:
        """初始化搜索回退。

        Args:
            llm_gateway: LLM Gateway 实例，用于生成搜索关键词。
                为 None 时降级为直接使用原始 query。
        """
        self._llm_gateway = llm_gateway

    async def should_fallback(
        self,
        local_results: list[Any],
    ) -> bool:
        """判断是否需要触发回退搜索。

        Args:
            local_results: 本地检索结果。

        Returns:
            是否需要回退。
        """
        return len(local_results) < self.MIN_RESULTS

    async def generate_search_keywords(
        self,
        original_query: str,
    ) -> str:
        """使用 LLM 生成优化的搜索关键词。

        Args:
            original_query: 用户原始查询。

        Returns:
            优化后的搜索关键词。LLM 不可用时返回原始查询。
        """
        if self._llm_gateway is None:
            logger.info("LLM Gateway 未配置，直接使用原始查询")
            return original_query

        try:
            prompt = (
                "你是一个搜索关键词优化助手。将以下用户查询优化为"
                "搜索引擎友好关键词（5-10 个词，用空格分隔，去除停用词）：\n\n"
                f"用户查询：{original_query}\n\n"
                "仅返回优化后的关键词，不要任何解释。"
            )
            resp = await self._llm_gateway.complete(
                prompt=prompt,
                task_type="default",
                layer="web_indexing",
                node="search_keyword_gen",
            )
            keywords = resp.content.strip()
            logger.info(
                "LLM 生成搜索关键词: %s → %s", original_query, keywords,
            )
            return keywords
        except Exception as exc:
            logger.warning(
                "LLM 关键词生成失败，降级为原始查询: %s - %s", original_query, exc,
            )
            return original_query

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, str]]:
        """执行网络搜索回退。

        Args:
            query: 搜索查询（会自动通过 LLM 生成优化关键词）。
            max_results: 最大返回结果数。

        Returns:
            搜索结果列表，每项包含 title / snippet / url。
        """
        # E11 增强：LLM 生成搜索关键词
        search_query = await self.generate_search_keywords(query)

        results: list[dict[str, str]] = []

        for url_template in _SEARCH_URLS:
            search_url = url_template.format(query=search_query)
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.get(
                        search_url,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (compatible; Prd2TsdBot/1.0)"
                            ),
                        },
                    )
                    if resp.status_code == 200:
                        results = self._parse_html_results(resp.text, max_results)
                        if results:
                            break
            except Exception as exc:
                logger.warning("搜索回退失败: %s - %s", query, exc)

        logger.info(
            "搜索回退完成: original_query=%s, search_query=%s, results=%d",
            query, search_query, len(results),
        )
        return results

    async def search_and_index(
        self,
        query: str,
        workspace_id: str = "",
        max_results: int = 5,
        vector_store: Any | None = None,
    ) -> list[dict[str, str]]:
        """执行搜索并将结果索引到 PGVector（E11 实时索引增强）。

        Args:
            query: 搜索查询。
            workspace_id: 工作空间 ID。
            max_results: 最大返回结果数。
            vector_store: PGVectorStore 实例。为 None 时跳过索引。

        Returns:
            搜索结果列表。
        """
        results = await self.search(query, max_results=max_results)

        # E11 增强：搜索结果实时索引到向量库
        if vector_store is not None and results:
            try:
                await vector_store.ensure_extensions()
                for i, r in enumerate(results):
                    snippet = r.get("snippet", "") or r.get("title", "")
                    if snippet:
                        chunk = Chunk(
                            id=f"web_search_{uuid.uuid4().hex[:12]}",
                            text=snippet,
                            level="paragraph",
                            section_path=f"web_search/{query[:50]}",
                            index=i,
                            metadata={
                                "source": "web_search_fallback",
                                "url": r.get("url", ""),
                                "title": r.get("title", ""),
                            },
                        )
                        embedder = EntityEmbedder()
                        chunk_emb = await embedder.embed_text(snippet)
                        await vector_store.upsert_chunk(chunk, chunk_emb)

                logger.info(
                    "搜索回退结果已索引: query=%s, indexed=%d", query, len(results),
                )
            except Exception as exc:
                logger.warning("搜索回退结果索引失败: %s - %s", query, exc)

        return results

    @staticmethod
    def _parse_html_results(html: str, max_results: int) -> list[dict[str, str]]:
        """从 HTML 搜索结果页提取信息。

        Args:
            html: 搜索结果页 HTML。
            max_results: 最大返回数。

        Returns:
            结果列表。
        """
        import re
        results: list[dict[str, str]] = []

        # DuckDuckGo HTML 结果格式：<a rel="nofollow" class="result__a" href="...">
        for m in re.finditer(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            html,
            re.IGNORECASE | re.DOTALL,
        ):
            if len(results) >= max_results:
                break
            url = m.group(1)
            title = re.sub(r'<[^>]+>', "", m.group(2)).strip()
            results.append({"title": title, "url": url, "snippet": ""})

        # 尝试提取 snippet
        for i, m in enumerate(
            re.finditer(
                r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                html,
                re.IGNORECASE | re.DOTALL,
            ),
        ):
            if i < len(results):
                results[i]["snippet"] = re.sub(r'<[^>]+>', "", m.group(1)).strip()

        return results
