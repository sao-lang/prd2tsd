"""Global Search 引擎 — 社区检测 → 社区报告 → LLM 聚合 → 宏观概括。"""

from __future__ import annotations

from typing import Any

from app.core.llm import llm_complete
from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import CommunityReport, ScoredDoc

logger = get_logger("prd2tsd.knowledge.global_search")

COMMUNITY_SUMMARY_PROMPT = """你是一个知识图谱分析专家。基于以下社区报告，给出宏观的系统架构概述。

社区报告：
{reports}

用户查询：{query}

请给出一个全面的总结，涵盖：
1. 系统的主要组件和技术栈
2. 各组件之间的关系
3. 架构模式和关键设计决策
4. 约束条件和技术选型理由"""


class GlobalSearchResult:
    """Global Search 结果。"""

    def __init__(
        self,
        answer: str,
        reports: list[CommunityReport],
        level: int,
    ) -> None:
        """初始化搜索结果。

        Args:
            answer: LLM 聚合后的答案。
            reports: 使用的社区报告列表。
            level: 使用的社区层级。
        """
        self.answer = answer
        self.reports = reports
        self.level = level


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

        Args:
            query: 用户查询。
            workspace_id: 工作空间 ID。

        Returns:
            Global Search 结果。
        """
        # 1. 获取社区报告
        reports = await self._get_community_reports(workspace_id)

        # 2. 选择合适层级
        level = self._select_level(query, reports)

        # 3. 筛选当前层级的报告
        level_reports = [r for r in reports if r.level == level][:self._top_k]

        # 4. LLM 聚合
        if level_reports:
            reports_text = "\n\n".join(
                f"社区 {r.community_id} (层级 {r.level}):\n{r.summary}\n"
                f"关键发现: {'; '.join(r.key_findings[:5])}"
                for r in level_reports
            )
            answer = await self._summarize(query, reports_text)
        else:
            answer = "未找到社区报告，无法生成宏观概括。"

        logger.info(
            "Global Search 完成: level=%d, reports=%d",
            level,
            len(level_reports),
        )

        return GlobalSearchResult(
            answer=answer,
            reports=level_reports,
            level=level,
        )

    async def _get_community_reports(self, workspace_id: str) -> list[CommunityReport]:
        """从 Neo4j 获取社区报告。

        如果图谱中没有社区报告，生成基础级别报告。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            社区报告列表。
        """
        cypher = "MATCH (cr:CommunityReport) RETURN cr"
        params: dict[str, Any] = {}
        if workspace_id:
            cypher = "MATCH (cr:CommunityReport {workspace_id: $workspace_id}) RETURN cr"
            params["workspace_id"] = workspace_id

        records = await self._graph_store.run_cypher(cypher, params)
        reports: list[CommunityReport] = []
        for record in records:
            props = dict(record["cr"])
            reports.append(
                CommunityReport(
                    id=props.get("id", ""),
                    community_id=props.get("community_id", ""),
                    level=int(props.get("level", 1)),
                    summary=props.get("summary", ""),
                    entities=props.get("entities", []),
                    key_findings=props.get("key_findings", []),
                    workspace_id=props.get("workspace_id", ""),
                )
            )

        # 无社区报告时创建基础报告
        if not reports:
            reports = await self._generate_base_reports(workspace_id)

        return reports

    async def _generate_base_reports(self, workspace_id: str) -> list[CommunityReport]:
        """从实体类型生成基础社区报告。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            基础社区报告列表。
        """
        entities = await self._graph_store.get_all_entities(workspace_id)
        if not entities:
            return []

        # 按类型分组作为社区
        groups: dict[str, list[str]] = {}
        for entity in entities:
            if entity.type not in groups:
                groups[entity.type] = []
            groups[entity.type].append(entity.name)

        reports: list[CommunityReport] = []
        for entity_type, names in groups.items():
            reports.append(
                CommunityReport(
                    id=f"base_{entity_type}",
                    community_id=f"type_{entity_type}",
                    level=1,
                    summary=f"类型 {entity_type} 包含 {len(names)} 个实体: {', '.join(names[:10])}",
                    entities=names,
                    key_findings=[f"发现 {len(names)} 个 {entity_type} 类型实体"],
                    workspace_id=workspace_id,
                )
            )
        return reports

    def _select_level(self, query: str, reports: list[CommunityReport]) -> int:
        """根据查询选择社区层级。

        宽泛查询选高层级（level 小），具体查询选低层级。

        Args:
            query: 用户查询。
            reports: 社区报告列表。

        Returns:
            选择的层级。
        """
        if not reports:
            return 1

        max_level = max(r.level for r in reports)
        # 宽泛查询关键词
        broad_keywords = ["整体", "架构", "概述", "总结", "所有", "全部"]
        query_lower = query.lower()

        for kw in broad_keywords:
            if kw in query_lower:
                return 1  # 最高层级

        # 具体查询选最低层级
        return max_level

    async def _summarize(self, query: str, reports_text: str) -> str:
        """使用 LLM 聚合社区报告生成答案。

        Args:
            query: 用户查询。
            reports_text: 社区报告文本。

        Returns:
            聚合后的答案。
        """
        try:
            response = await llm_complete(
                prompt=COMMUNITY_SUMMARY_PROMPT.format(
                    reports=reports_text[:4000],
                    query=query,
                ),
                model=self._model,
                temperature=0.3,
                max_tokens=2048,
            )
            return response
        except Exception as e:
            logger.warning("Global Search 聚合失败: %s", str(e))
            return f"基于社区报告的分析（查询: {query}）:\n\n{reports_text[:1000]}"

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
                metadata={"level": result.level, "reports": len(result.reports)},
            )
        ]
