"""单元测试 — 知识图谱版本控制。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.ingestion.kg_versioning import KnowledgeGraphVersioning


class TestKnowledgeGraphVersioning:
    """版本控制测试。"""

    @pytest.fixture
    def graph_store_mock(self) -> MagicMock:
        """创建 Mock 图存储。"""
        mock = MagicMock(spec=Neo4jGraphStore)
        mock.run_cypher = AsyncMock(return_value=[])
        return mock

    async def test_create_snapshot(self, graph_store_mock) -> None:
        """验证创建快照。"""
        versioning = KnowledgeGraphVersioning(graph_store=graph_store_mock)
        # Mock _export_graph 返回空数据
        versioning._export_graph = AsyncMock(return_value=([], []))  # type: ignore[assignment]
        version_id = await versioning.create_snapshot("test snapshot")
        assert version_id is not None
        assert len(version_id) > 0

    async def test_list_snapshots(self, graph_store_mock) -> None:
        """验证列出快照。"""
        graph_store_mock.run_cypher = AsyncMock(
            return_value=[{"v": {"id": "v1", "name": "snap1", "created_at": "2024-01-01"}}]
        )
        versioning = KnowledgeGraphVersioning(graph_store=graph_store_mock)
        snapshots = await versioning.list_snapshots()
        assert isinstance(snapshots, list)

    async def test_rollback_nonexistent(self, graph_store_mock) -> None:
        """验证回滚不存在的快照返回 False。"""
        graph_store_mock.run_cypher = AsyncMock(return_value=[])
        versioning = KnowledgeGraphVersioning(graph_store=graph_store_mock)
        result = await versioning.rollback("nonexistent")
        assert result is False
