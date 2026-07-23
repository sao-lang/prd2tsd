"""单元测试 — Global Search。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGEntity
from app.knowledge_layer.retrieval.global_search import GlobalSearch


class TestGlobalSearch:
    """Global Search 测试。"""

    @pytest.fixture
    def graph_store_mock(self) -> MagicMock:
        """创建 Mock 图存储。"""
        mock = MagicMock(spec=Neo4jGraphStore)
        mock.run_cypher = AsyncMock(return_value=[])
        mock.get_all_entities = AsyncMock(
            return_value=[
                KGEntity(id="e1", name="Spring Boot", type="TechStack"),
                KGEntity(id="e2", name="PostgreSQL", type="TechStack"),
                KGEntity(id="e3", name="UserService", type="Component"),
            ]
        )
        return mock

    async def test_search_returns_answer(self, graph_store_mock) -> None:
        """验证 Global Search 返回答案。"""
        searcher = GlobalSearch(graph_store=graph_store_mock)
        result = await searcher.search("整体架构")
        assert result.answer is not None

    async def test_search_as_docs(self, graph_store_mock) -> None:
        """验证 Global Search 返回 ScoredDoc。"""
        searcher = GlobalSearch(graph_store=graph_store_mock)
        docs = await searcher.search_as_docs("整体架构")
        assert len(docs) > 0
        assert docs[0].source == "global"

    async def test_base_reports_generation(self, graph_store_mock) -> None:
        """验证基础社区报告生成。"""
        searcher = GlobalSearch(graph_store=graph_store_mock)
        reports = await searcher._generate_base_reports(workspace_id="")
        assert len(reports) > 0
        # 至少应有 TechStack 和 Component 两个社区
        types = {r.community_id for r in reports}
        assert len(types) >= 2
