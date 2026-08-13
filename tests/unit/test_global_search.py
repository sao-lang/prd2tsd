"""单元测试 — Global Search。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
        """验证 Global Search 返回宏观总结答案。"""
        searcher = GlobalSearch(graph_store=graph_store_mock)
        with patch("app.knowledge_layer.retrieval.global_search.gateway") as mock_gateway:
            mock_gateway.complete = AsyncMock(
                return_value=MagicMock(content="宏观架构总结：Spring Boot + PostgreSQL 微服务架构"),
            )
            result = await searcher.search("整体架构")
        assert result.answer is not None
        assert "宏观" in result.answer

    async def test_search_returns_answer_when_no_entities(self) -> None:
        """验证无实体时返回降级提示。"""
        mock = MagicMock(spec=Neo4jGraphStore)
        mock.get_all_entities = AsyncMock(return_value=[])
        searcher = GlobalSearch(graph_store=mock)
        result = await searcher.search("整体架构")
        assert "未找到知识实体" in result.answer

    async def test_search_as_docs(self, graph_store_mock) -> None:
        """验证 Global Search 返回 ScoredDoc（source=global）。"""
        searcher = GlobalSearch(graph_store=graph_store_mock)
        with patch("app.knowledge_layer.retrieval.global_search.gateway") as mock_gateway:
            mock_gateway.complete = AsyncMock(return_value=MagicMock(content="宏观总结"))
            docs = await searcher.search_as_docs("整体架构")
        assert len(docs) > 0
        assert docs[0].source == "global"
        assert docs[0].id == "global_summary"

    async def test_group_by_type(self, graph_store_mock) -> None:
        """验证实体按类型聚合。"""
        searcher = GlobalSearch(graph_store=graph_store_mock)
        entities = await graph_store_mock.get_all_entities("")
        groups = searcher._group_by_type(entities)
        assert set(groups.keys()) == {"TechStack", "Component"}
        assert "Spring Boot" in groups["TechStack"]
        assert "UserService" in groups["Component"]
