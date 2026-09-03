"""知识图谱关系写入和老化策略测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.aging import KnowledgeAgingPolicy
from app.knowledge_layer.config import KnowledgeLayerConfig
from app.knowledge_layer.graph_store import Neo4jGraphStore
from app.knowledge_layer.models import KGRelation, KnowledgeAgingStats


def _driver_with_session(session: MagicMock) -> MagicMock:
    """构造支持 async context manager 的 Neo4j Driver。"""
    driver = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    driver.session.return_value = context
    return driver


@pytest.mark.asyncio
async def test_upsert_relation_uses_fixed_type_and_properties() -> None:
    """关系类型必须参数化存储，不能把模型输出拼入 Cypher。"""
    result = MagicMock()
    result.single = AsyncMock(return_value={"id": "r1"})
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    store = Neo4jGraphStore(driver=_driver_with_session(session))
    relation = KGRelation(
        id="r1",
        source_entity_id="source",
        target_entity_id="target",
        relation_type="uses`) MATCH (n) DETACH DELETE n //",
        workspace_id="ws-1",
    )

    relation_id = await store.upsert_relation(relation)

    assert relation_id == "r1"
    query = session.run.await_args.args[0]
    assert "[r:RELATED" in query
    assert relation.relation_type not in query
    assert session.run.await_args.kwargs["relation_type"] == relation.relation_type


@pytest.mark.asyncio
async def test_upsert_relation_fails_when_endpoint_is_missing() -> None:
    """端点不存在时关系写入应显式失败。"""
    result = MagicMock()
    result.single = AsyncMock(return_value=None)
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    store = Neo4jGraphStore(driver=_driver_with_session(session))

    with pytest.raises(ValueError, match="关系端点不存在"):
        await store.upsert_relation(
            KGRelation(source_entity_id="missing", target_entity_id="target", workspace_id="ws-1")
        )


@pytest.mark.asyncio
async def test_aging_policy_calculates_all_cutoffs() -> None:
    """老化策略应按配置计算 90/180/365 天边界。"""
    graph_store = MagicMock()
    graph_store.apply_aging = AsyncMock(return_value=KnowledgeAgingStats(downgraded_entities=2))
    config = KnowledgeLayerConfig(downgrade_days=90, archive_days=180, soft_delete_days=365)
    now = datetime(2026, 9, 3, tzinfo=UTC)

    stats = await KnowledgeAgingPolicy(graph_store=graph_store, config=config).run("ws-1", now=now)

    assert stats.downgraded_entities == 2
    kwargs = graph_store.apply_aging.await_args.kwargs
    assert kwargs["workspace_id"] == "ws-1"
    assert kwargs["downgrade_before_ms"] == int(datetime(2026, 6, 5, tzinfo=UTC).timestamp() * 1000)
    assert kwargs["archive_before_ms"] == int(datetime(2026, 3, 7, tzinfo=UTC).timestamp() * 1000)
    assert kwargs["soft_delete_before_ms"] == int(datetime(2025, 9, 3, tzinfo=UTC).timestamp() * 1000)


@pytest.mark.asyncio
async def test_graph_aging_processes_oldest_state_first() -> None:
    """老化执行顺序必须是软删除、归档、降级，实体与关系一致。"""
    results: list[MagicMock] = []
    for count in (0, 0, 3, 2, 1, 6, 5, 4):
        result = MagicMock()
        result.single = AsyncMock(return_value={"changed": count})
        results.append(result)
    session = MagicMock()
    session.run = AsyncMock(side_effect=results)
    store = Neo4jGraphStore(driver=_driver_with_session(session))

    stats = await store.apply_aging(30, 20, 10, workspace_id="ws-1")

    assert stats.model_dump() == {
        "downgraded_entities": 1,
        "archived_entities": 2,
        "deleted_entities": 3,
        "downgraded_relations": 4,
        "archived_relations": 5,
        "deleted_relations": 6,
    }
    queries = [call.args[0] for call in session.run.await_args_list]
    assert "e.updated_at IS NULL" in queries[0]
    assert "r.updated_at IS NULL" in queries[1]
    assert "SET e.status = 'deleted'" in queries[2]
    assert "SET e.status = 'archived'" in queries[3]
    assert "SET e.status = 'downgraded'" in queries[4]
    assert "SET r.status = 'deleted'" in queries[5]
