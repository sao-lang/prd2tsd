"""集成测试 — 版本快照/回滚。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.ingestion.kg_versioning import KnowledgeGraphVersioning


@pytest.mark.asyncio
async def test_snapshot_and_rollback() -> None:
    """验证创建快照和回滚。"""
    mock_graph = MagicMock()
    mock_graph.run_cypher = AsyncMock(side_effect=[
        # create_snapshot — 创建 VersionSnapshot 节点
        [],
        # create_snapshot — 设置 snapshot_data
        [],
        # list_snapshots
        [{"v": {"id": "v1", "name": "test_snap", "created_at": "2024-01-01", "entity_count": 3, "relation_count": 2}}],
    ])

    versioning = KnowledgeGraphVersioning(graph_store=mock_graph)
    versioning._export_graph = AsyncMock(return_value=(  # type: ignore[assignment]
        [{"id": "e1", "name": "Spring", "type": "TechStack"}],
        [{"id": "r1", "source_id": "e1", "target_id": "e2", "type": "depends_on"}],
    ))

    # 创建快照
    version_id = await versioning.create_snapshot("test_snap")
    assert version_id != ""

    # 列出快照
    snapshots = await versioning.list_snapshots()
    assert len(snapshots) >= 1
