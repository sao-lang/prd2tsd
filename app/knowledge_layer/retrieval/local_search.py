"""Local Search 引擎 — 实体匹配 → 子图遍历 → TextUnit 原文证据 → 上下文组装。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGEntity, ScoredDoc, TextUnit

logger = get_logger("prd2tsd.knowledge.local_search")


class LocalSearchResult:
    """Local Search 结果。"""

    def __init__(
        self,
        matched_entities: list[KGEntity],
        text_unit_evidence: list[TextUnit],
        context: str,
    ) -> None:
        """初始化搜索结果。

        Args:
            matched_entities: 匹配的实体列表。
            text_unit_evidence: 原文证据列表。
            context: 组装后的上下文文本。
        """
        self.matched_entities = matched_entities
        self.text_unit_evidence = text_unit_evidence
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
    ) -> LocalSearchResult:
        """执行 Local Search。

        Args:
            query: 搜索查询。
            workspace_id: 工作空间 ID。
            top_k: 返回结果数。

        Returns:
            Local Search 结果。
        """
        k = top_k or self._top_k

        # 1. 实体匹配
        import re

        keywords = re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", query)
        matched_entities: list[KGEntity] = []
        seen_ids: set[str] = set()

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

        # 3. 构建 TextUnit 证据
        text_unit_evidence: list[TextUnit] = []
        for entity in matched_entities + neighbor_entities:
            if entity.source_text_unit_id:
                text_unit_evidence.append(
                    TextUnit(
                        id=entity.source_text_unit_id,
                        text="",
                        entities=[entity.id],
                        section_path="",
                    )
                )

        # 4. 组装上下文
        context = self._assemble_context(
            query=query,
            matched_entities=matched_entities,
            neighbor_entities=neighbor_entities,
            text_unit_evidence=text_unit_evidence[:k],
        )

        logger.info(
            "Local Search 完成: %d entities, %d neighbors, %d text_units",
            len(matched_entities),
            len(neighbor_entities),
            len(text_unit_evidence),
        )

        return LocalSearchResult(
            matched_entities=matched_entities + neighbor_entities,
            text_unit_evidence=text_unit_evidence[:k],
            context=context,
        )

    def _assemble_context(
        self,
        query: str,
        matched_entities: list[KGEntity],
        neighbor_entities: list[KGEntity],
        text_unit_evidence: list[TextUnit],
    ) -> str:
        """将检索结果组装成结构化上下文。

        Args:
            query: 原始查询。
            matched_entities: 匹配的实体。
            neighbor_entities: 邻接实体。
            text_unit_evidence: TextUnit 证据。

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

        if text_unit_evidence:
            parts.append("### 原文证据\n")
            for tu in text_unit_evidence[:5]:
                parts.append(f"- [{tu.id}] {tu.text[:200]}")
            parts.append("")

        return "\n".join(parts)

    async def search_as_docs(
        self,
        query: str,
        workspace_id: str = "",
        top_k: int | None = None,
    ) -> list[ScoredDoc]:
        """执行 Local Search 并返回 ScoredDoc 列表。

        Args:
            query: 搜索查询。
            workspace_id: 工作空间 ID。
            top_k: 返回结果数。

        Returns:
            ScoredDoc 列表。
        """
        result = await self.search(query, workspace_id, top_k)
        docs: list[ScoredDoc] = []
        for i, tu in enumerate(result.text_unit_evidence):
            docs.append(
                ScoredDoc(
                    id=tu.id,
                    text=tu.text,
                    score=1.0 - (i * 0.1),
                    source="local",
                    metadata={"entity_count": len(result.matched_entities)},
                )
            )
        if not docs:
            docs.append(
                ScoredDoc(
                    id="local_context",
                    text=result.context,
                    score=0.5,
                    source="local",
                )
            )
        return docs
