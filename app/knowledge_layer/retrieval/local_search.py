"""Local Search 引擎 — 实体匹配 → 子图遍历 → 上下文组装。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGEntity, ScoredDoc

logger = get_logger("prd2tsd.knowledge.local_search")


class LocalSearchResult:
    """Local Search 结果。"""

    def __init__(
        self,
        matched_entities: list[KGEntity],
        source_entity_ids: list[str],
        context: str,
    ) -> None:
        """初始化搜索结果。

        Args:
            matched_entities: 匹配的实体列表。
            source_entity_ids: 有原文来源的实体 ID 列表。
            context: 组装后的上下文文本。
        """
        self.matched_entities = matched_entities
        self.source_entity_ids = source_entity_ids
        self.context = context


class LocalSearch:
    """Local Search 引擎。"""

    def __init__(
        self,
        graph_store: Neo4jGraphStore | None = None,
    ) -> None:
        """初始化 Local Search。

        Args:
            graph_store: Neo4j 图存储。为 None 时创建新实例。
        """
        self._graph_store = graph_store or Neo4jGraphStore()
        self._top_k = kn_config.local_top_k

    async def search(
        self,
        query: str,
        workspace_id: str = "",
        top_k: int | None = None,
        seed_entity_ids: list[str] | None = None,
    ) -> LocalSearchResult:
        """执行 Local Search。

        Args:
            query: 搜索查询。
            workspace_id: 工作空间 ID。
            top_k: 返回结果数。
            seed_entity_ids: 实体链接命中的实体 ID（可选），优先作为中心实体参与遍历。

        Returns:
            Local Search 结果。
        """
        k = top_k or self._top_k

        # 0. 实体链接种子：优先把链接精确命中的实体作为中心实体（与关键词匹配互补去重）
        matched_entities: list[KGEntity] = []
        seen_ids: set[str] = set()
        if seed_entity_ids:
            seed_entities = await self._graph_store.get_entities_by_ids(
                seed_entity_ids,
                workspace_id,
            )
            for entity in seed_entities:
                if entity.id not in seen_ids:
                    seen_ids.add(entity.id)
                    matched_entities.append(entity)

        # 1. 实体匹配
        import re

        keywords = re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", query)

        for keyword in keywords:
            if len(keyword) < 2:
                continue
            entities = await self._graph_store.search_entities(
                query=keyword,
                workspace_id=workspace_id,
                limit=k,
            )
            for entity in entities:
                if entity.id not in seen_ids:
                    seen_ids.add(entity.id)
                    matched_entities.append(entity)

        # 2. 子图遍历（1-2 跳）
        neighbor_entities: list[KGEntity] = []
        for entity in matched_entities[:5]:  # 限制中心实体数
            neighbors = await self._graph_store.get_neighbors(
                entity_id=entity.id,
                max_depth=2,
                workspace_id=workspace_id,
            )
            for n in neighbors:
                if n.id not in seen_ids:
                    seen_ids.add(n.id)
                    neighbor_entities.append(n)

        # 3. 收集有原文来源的实体 ID
        source_entity_ids: list[str] = []
        for entity in matched_entities + neighbor_entities:
            if entity.source_text_unit_id and entity.id not in source_entity_ids:
                source_entity_ids.append(entity.id)

        # 4. 组装上下文
        context = self._assemble_context(
            query=query,
            matched_entities=matched_entities,
            neighbor_entities=neighbor_entities,
            source_entity_ids=source_entity_ids[:k],
        )

        logger.info(
            "Local Search 完成: %d entities, %d neighbors, %d sources",
            len(matched_entities),
            len(neighbor_entities),
            len(source_entity_ids),
        )

        return LocalSearchResult(
            matched_entities=matched_entities + neighbor_entities,
            source_entity_ids=source_entity_ids[:k],
            context=context,
        )

    def _assemble_context(
        self,
        query: str,
        matched_entities: list[KGEntity],
        neighbor_entities: list[KGEntity],
        source_entity_ids: list[str],
    ) -> str:
        """将检索结果组装成结构化上下文。

        Args:
            query: 原始查询。
            matched_entities: 匹配的实体。
            neighbor_entities: 邻接实体。
            source_entity_ids: 有原文来源的实体 ID 列表。

        Returns:
            组装后的上下文文本。
        """
        parts: list[str] = [f"## 查询: {query}\n"]

        if matched_entities:
            parts.append("### 匹配实体\n")
            for e in matched_entities:
                parts.append(f"- {e.name} ({e.type}): {e.description[:100]}")
            parts.append("")

        if neighbor_entities:
            parts.append("### 相关实体\n")
            for e in neighbor_entities[:10]:
                parts.append(f"- {e.name} ({e.type})")
            parts.append("")

        if source_entity_ids:
            parts.append("### 原文来源\n")
            for eid in source_entity_ids[:5]:
                parts.append(f"- 实体 {eid}")
            parts.append("")

        return "\n".join(parts)

    async def search_as_docs(
        self,
        query: str,
        workspace_id: str = "",
        top_k: int | None = None,
        seed_entity_ids: list[str] | None = None,
    ) -> list[ScoredDoc]:
        """执行 Local Search 并返回 ScoredDoc 列表。

        Args:
            query: 搜索查询。
            workspace_id: 工作空间 ID。
            top_k: 返回结果数。
            seed_entity_ids: 实体链接命中的实体 ID（可选），透传给 search。

        Returns:
            ScoredDoc 列表。
        """
        result = await self.search(query, workspace_id, top_k, seed_entity_ids)
        docs: list[ScoredDoc] = []
        for i, ent in enumerate(result.matched_entities):
            docs.append(
                ScoredDoc(
                    id=ent.id,
                    text=ent.name,
                    score=1.0 - (i * 0.1),
                    source="local",
                    metadata={
                        "entity_count": len(result.matched_entities),
                        "entity_type": getattr(ent, "entity_type", getattr(ent, "type", "")),
                    },
                )
            )
        if not docs and result.context:
            docs.append(
                ScoredDoc(
                    id="local_context",
                    text=result.context,
                    score=0.5,
                    source="local",
                )
            )
        return docs
