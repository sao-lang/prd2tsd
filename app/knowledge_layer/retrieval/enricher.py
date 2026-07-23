"""Query Enricher — 实体链接扩展。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.knowledge_layer.graph_store import Neo4jGraphStore

logger = get_logger("prd2tsd.knowledge.enricher")


class QueryEnricher:
    """Query Enricher — 通过实体链接扩展查询。"""

    def __init__(self, graph_store: Neo4jGraphStore | None = None) -> None:
        """初始化查询丰富器。

        Args:
            graph_store: Neo4j 图存储。为 None 时创建新实例。
        """
        self._graph_store = graph_store or Neo4jGraphStore()

    async def enrich(
        self,
        query: str,
        workspace_id: str = "",
    ) -> tuple[str, list[str]]:
        """丰富查询 — 通过实体链接扩展。

        Args:
            query: 原始查询。
            workspace_id: 工作空间 ID。

        Returns:
            (扩展后的查询, 匹配的实体 ID 列表)。
        """
        # 从查询中提取关键词
        import re

        keywords = re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", query)
        matched_entity_ids: list[str] = []

        for keyword in keywords:
            if len(keyword) < 2:
                continue
            entities = await self._graph_store.search_entities(
                query=keyword,
                workspace_id=workspace_id,
                limit=3,
            )
            for entity in entities:
                if entity.id not in matched_entity_ids:
                    matched_entity_ids.append(entity.id)

        if matched_entity_ids:
            enriched = f"{query} (entities: {', '.join(matched_entity_ids[:5])})"
            logger.debug("查询丰富: %s -> %s", query, enriched)
            return enriched, matched_entity_ids

        return query, []
