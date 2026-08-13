"""Global Search 引擎 — 实体按类型聚合 → LLM 宏观总结。

Global Search 保留"宏观总结"价值：拉取全部实体，按实体类型聚合，
再由 LLM 生成宏观系统架构概述（社区检测/社区报告逻辑已简化删除）。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import ScoredDoc
from app.llm_gateway import gateway

logger = get_logger("prd2tsd.knowledge.global_search")

GLOBAL_SUMMARY_PROMPT = """你是一个知识图谱分析专家。基于以下按实体类型聚合的知识实体，给出宏观的系统架构概述。

聚合实体：
{entities}

用户查询：{query}

请给出一个全面的总结，涵盖：
1. 系统的主要组件和技术栈
2. 各组件之间的关系
3. 架构模式和关键设计决策
4. 约束条件和技术选型理由"""


class GlobalSearchResult:
    """Global Search 结果。"""

    def __init__(self, answer: str) -> None:
        """初始化搜索结果。

        Args:
            answer: LLM 聚合后的答案。
        """
        self.answer = answer


class GlobalSearch:
    """Global Search 引擎。"""

    def __init__(
        self,
        graph_store: Neo4jGraphStore | None = None,
        model: str | None = None,
    ) -> None:
        """初始化 Global Search。

        Args:
            graph_store: Neo4j 图存储。为 None 时创建新实例。
            model: LLM 模型名。
        """
        self._graph_store = graph_store or Neo4jGraphStore()
        self._model = model
        self._top_k = kn_config.global_top_k

    async def search(
        self,
        query: str,
        workspace_id: str = "",
    ) -> GlobalSearchResult:
        """执行 Global Search。

        拉取全部实体 → 按实体类型聚合 → LLM 生成宏观总结。

        Args:
            query: 用户查询。
            workspace_id: 工作空间 ID。

        Returns:
            Global Search 结果。
        """
        # 1. 获取全部实体
        entities = await self._graph_store.get_all_entities(workspace_id)

        # 2. 按实体类型聚合
        groups = self._group_by_type(entities)

        # 3. LLM 聚合生成宏观总结
        if groups:
            entities_text = "\n\n".join(
                f"类型 {entity_type} ({len(names)} 个): {', '.join(names[:10])}"
                for entity_type, names in groups.items()
            )
            answer = await self._summarize(query, entities_text)
        else:
            answer = "未找到知识实体，无法生成宏观概括。"

        logger.info("Global Search 完成: groups=%d", len(groups))

        return GlobalSearchResult(answer=answer)

    def _group_by_type(self, entities: list[Any]) -> dict[str, list[str]]:
        """按实体类型分组聚合实体名称。

        Args:
            entities: 知识实体列表。

        Returns:
            {实体类型: [实体名]} 映射（按实体数降序，最多取 top_k 个类型）。
        """
        groups: dict[str, list[str]] = {}
        for entity in entities:
            if entity.type not in groups:
                groups[entity.type] = []
            groups[entity.type].append(entity.name)
        # 按实体数降序，取前 top_k 个类型
        return dict(
            sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)[: self._top_k]
        )

    async def _summarize(self, query: str, entities_text: str) -> str:
        """使用 LLM 聚合实体生成宏观总结。

        Args:
            query: 用户查询。
            entities_text: 按类型聚合的实体文本。

        Returns:
            聚合后的答案。
        """
        try:
            resp = await gateway.complete(
                prompt=GLOBAL_SUMMARY_PROMPT.format(
                    entities=entities_text[:4000],
                    query=query,
                ),
                task_type="default",
                layer="knowledge",
                node="global_search",
                model=self._model,
                temperature=0.3,
                max_tokens=2048,
            )
            return resp.content
        except Exception as e:
            logger.warning("Global Search 聚合失败: %s", str(e))
            return f"基于知识实体的分析（查询: {query}）:\n\n{entities_text[:1000]}"

    async def search_as_docs(
        self,
        query: str,
        workspace_id: str = "",
    ) -> list[ScoredDoc]:
        """执行 Global Search 并返回 ScoredDoc 列表。

        Args:
            query: 搜索查询。
            workspace_id: 工作空间 ID。

        Returns:
            ScoredDoc 列表。
        """
        result = await self.search(query, workspace_id)
        return [
            ScoredDoc(
                id="global_summary",
                text=result.answer,
                score=1.0,
                source="global",
                metadata={"source": "global"},
            )
        ]
