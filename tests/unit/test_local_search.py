"""单元测试 — Local Search。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGEntity, ScoredDoc
from app.knowledge_layer.retrieval.local_search import LocalSearch


class TestLocalSearch:
    """Local Search 测试。"""

    @pytest.fixture
    def graph_store_mock(self) -> MagicMock:
        """创建 Mock 图存储。"""
        mock = MagicMock(spec=Neo4jGraphStore)
        mock.search_entities = AsyncMock(
            return_value=[
                KGEntity(id="e1", name="Spring Boot", type="TechStack", description="Java framework"),
                KGEntity(id="e2", name="PostgreSQL", type="TechStack", description="Database"),
            ]
        )
        mock.get_neighbors = AsyncMock(return_value=[])
        return mock

    async def test_search_returns_entities(self, graph_store_mock) -> None:
        """验证 Local Search 返回匹配实体。"""
        searcher = LocalSearch(graph_store=graph_store_mock)
        result = await searcher.search("Spring Boot")
        assert len(result.matched_entities) > 0
        assert any("Spring" in e.name for e in result.matched_entities)

    async def test_search_as_docs(self, graph_store_mock) -> None:
        """验证 Local Search 返回 ScoredDoc。"""
        searcher = LocalSearch(graph_store=graph_store_mock)
        docs = await searcher.search_as_docs("PostgreSQL")
        assert isinstance(docs, list)
        if docs:
            assert isinstance(docs[0], ScoredDoc)

    async def test_search_empty_query(self, graph_store_mock) -> None:
        """验证空查询的处理。"""
        searcher = LocalSearch(graph_store=graph_store_mock)
        result = await searcher.search("")
        assert result.context is not None

    async def test_search_with_seed_entity_ids(self, graph_store_mock) -> None:
        """验证实体链接种子优先作为中心实体参与检索。"""
        seed = KGEntity(
            id="seed-1",
            name="PostgreSQL",
            type="TechStack",
            description="Database",
        )
        graph_store_mock.get_entities_by_ids = AsyncMock(return_value=[seed])
        graph_store_mock.search_entities = AsyncMock(return_value=[])
        searcher = LocalSearch(graph_store=graph_store_mock)

        result = await searcher.search("PostgreSQL", seed_entity_ids=["seed-1"])

        graph_store_mock.get_entities_by_ids.assert_awaited_once_with(["seed-1"], "")
        assert result.matched_entities[0].id == "seed-1"

    async def test_search_as_docs_passes_seed_entity_ids(self, graph_store_mock) -> None:
        """验证 search_as_docs 将种子实体 ID 透传给 search。"""
        seed = KGEntity(
            id="seed-1",
            name="PostgreSQL",
            type="TechStack",
            description="Database",
        )
        graph_store_mock.get_entities_by_ids = AsyncMock(return_value=[seed])
        graph_store_mock.search_entities = AsyncMock(return_value=[])
        searcher = LocalSearch(graph_store=graph_store_mock)

        docs = await searcher.search_as_docs(
            "PostgreSQL",
            workspace_id="ws-1",
            seed_entity_ids=["seed-1"],
        )

        graph_store_mock.get_entities_by_ids.assert_awaited_once_with(["seed-1"], "ws-1")
        assert any(doc.id == "seed-1" for doc in docs)
