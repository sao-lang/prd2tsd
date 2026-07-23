"""集成测试 — Local Search。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGEntity
from app.knowledge_layer.retrieval.local_search import LocalSearch


@pytest.mark.asyncio
async def test_local_search_returns_entities() -> None:
    """验证 Local Search 返回匹配实体。"""
    mock_graph = MagicMock(spec=Neo4jGraphStore)
    mock_graph.search_entities = AsyncMock(
        return_value=[
            KGEntity(id="e1", name="用户服务", type="Component", description="用户 CRUD 服务"),
            KGEntity(id="e2", name="JWT 认证", type="TechStack", description="JWT 身份认证"),
        ]
    )
    mock_graph.get_neighbors = AsyncMock(return_value=([], []))

    searcher = LocalSearch(graph_store=mock_graph)
    result = await searcher.search("用户服务")
    assert len(result.matched_entities) > 0
    assert any("用户" in e.name for e in result.matched_entities)


@pytest.mark.asyncio
async def test_local_search_returns_evidence() -> None:
    """验证 Local Search 返回原文证据。"""
    mock_graph = MagicMock(spec=Neo4jGraphStore)
    mock_graph.search_entities = AsyncMock(
        return_value=[
            KGEntity(
                id="e1",
                name="JWT",
                type="TechStack",
                description="JWT Token 认证",
                source_text_unit_id="tu1",
            ),
        ]
    )
    mock_graph.get_neighbors = AsyncMock(return_value=([], []))

    searcher = LocalSearch(graph_store=mock_graph)
    result = await searcher.search("JWT 认证")
    assert result.context is not None
    assert len(result.context) > 0
