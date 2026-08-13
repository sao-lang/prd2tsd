"""集成测试 — Global Search。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGEntity
from app.knowledge_layer.retrieval.global_search import GlobalSearch


@pytest.mark.asyncio
async def test_global_search_returns_summary() -> None:
    """验证 Global Search 返回宏观总结。"""
    mock_graph = MagicMock(spec=Neo4jGraphStore)
    mock_graph.run_cypher = AsyncMock(return_value=[])
    mock_graph.get_all_entities = AsyncMock(
        return_value=[
            KGEntity(id="e1", name="Spring Boot", type="TechStack"),
            KGEntity(id="e2", name="PostgreSQL", type="TechStack"),
            KGEntity(id="e3", name="UserService", type="Component"),
            KGEntity(id="e4", name="AuthService", type="Component"),
            KGEntity(id="e5", name="微服务架构", type="ArchitecturePattern"),
        ]
    )

    searcher = GlobalSearch(graph_store=mock_graph)
    with patch("app.knowledge_layer.retrieval.global_search.gateway") as mock_gateway:
        mock_gateway.complete = AsyncMock(return_value=MagicMock(content="宏观架构总结"))
        result = await searcher.search("整体架构")

    assert result.answer is not None
    assert len(result.answer) > 0
    # 宏观总结应能覆盖整体架构类查询
    assert any(k in result.answer for k in ["宏观", "架构"])


@pytest.mark.asyncio
async def test_global_search_group_by_type() -> None:
    """验证实体按类型聚合为宏观总结输入。"""
    mock_graph = MagicMock(spec=Neo4jGraphStore)
    mock_graph.run_cypher = AsyncMock(return_value=[])
    mock_graph.get_all_entities = AsyncMock(
        return_value=[
            KGEntity(id="e1", name="Spring Boot", type="TechStack"),
            KGEntity(id="e2", name="AuthService", type="Component"),
        ]
    )

    searcher = GlobalSearch(graph_store=mock_graph)
    entities = await mock_graph.get_all_entities("")
    groups = searcher._group_by_type(entities)
    assert set(groups.keys()) == {"TechStack", "Component"}
