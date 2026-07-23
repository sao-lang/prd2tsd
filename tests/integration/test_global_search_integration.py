"""集成测试 — Global Search。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGEntity
from app.knowledge_layer.retrieval.global_search import GlobalSearch


@pytest.mark.asyncio
async def test_global_search_returns_summary() -> None:
    """验证 Global Search 返回社区报告摘要。"""
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
    result = await searcher.search("整体架构")

    assert result.answer is not None
    assert len(result.answer) > 0
    assert result.level >= 1


@pytest.mark.asyncio
async def test_global_search_level_selection() -> None:
    """验证层级选择逻辑。"""
    mock_graph = MagicMock(spec=Neo4jGraphStore)
    mock_graph.run_cypher = AsyncMock(return_value=[])
    mock_graph.get_all_entities = AsyncMock(return_value=[])

    searcher = GlobalSearch(graph_store=mock_graph)

    # 宽泛查询 — 选最高层级
    level = searcher._select_level("整体架构", [])
    assert level >= 1
