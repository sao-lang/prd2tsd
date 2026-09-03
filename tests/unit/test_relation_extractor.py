"""知识关系抽取器单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.knowledge_layer.ingestion.relation_extractor import RelationExtractor
from app.knowledge_layer.models import Chunk, KGEntity


@pytest.mark.asyncio
async def test_extract_binds_resolved_endpoints_and_is_stable() -> None:
    """合法端点应绑定消歧 ID，相同关系重复抽取保持同一 ID。"""
    chunk = Chunk(id="c1", text="服务使用 Postgres 存储数据。", index=0)
    source_entities = [
        KGEntity(id="new-1", name="服务", type="Component", source_text_unit_id="c1"),
        KGEntity(id="new-2", name="Postgres", type="TechStack", source_text_unit_id="c1"),
    ]
    resolved_entities = [
        KGEntity(id="service-id", name="服务", type="Component"),
        KGEntity(id="postgres-id", name="PostgreSQL", type="TechStack"),
    ]
    response = MagicMock(
        content=(
            '[{"source":"服务","target":"Postgres","relation_type":"STORES IN",'
            '"description":"数据持久化","confidence":0.9}]'
        ),
        metadata={},
    )

    with patch(
        "app.knowledge_layer.ingestion.relation_extractor.gateway.complete",
        new=AsyncMock(return_value=response),
    ) as complete:
        extractor = RelationExtractor()
        first = await extractor.extract([chunk], source_entities, resolved_entities, "ws-1")
        second = await extractor.extract([chunk], source_entities, resolved_entities, "ws-1")

    assert len(first) == 1
    assert first[0].id == second[0].id
    assert first[0].source_entity_id == "service-id"
    assert first[0].target_entity_id == "postgres-id"
    assert first[0].relation_type == "stores_in"
    assert complete.await_args.kwargs["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_extract_rejects_hallucinated_endpoint() -> None:
    """模型创造候选集合外实体时不得写入关系。"""
    chunk = Chunk(id="c1", text="API 使用 Redis。")
    entities = [
        KGEntity(id="api", name="API", type="Component", source_text_unit_id="c1"),
        KGEntity(id="redis", name="Redis", type="TechStack", source_text_unit_id="c1"),
    ]
    response = MagicMock(
        content='[{"source":"API","target":"MySQL","relation_type":"uses"}]',
        metadata={},
    )

    with patch(
        "app.knowledge_layer.ingestion.relation_extractor.gateway.complete",
        new=AsyncMock(return_value=response),
    ):
        relations = await RelationExtractor().extract([chunk], entities, entities, "ws-1")

    assert relations == []


@pytest.mark.asyncio
async def test_extract_skips_chunk_with_fewer_than_two_entities() -> None:
    """不足两个候选实体时不应浪费一次 LLM 调用。"""
    chunk = Chunk(id="c1", text="Redis。")
    entities = [KGEntity(id="redis", name="Redis", type="TechStack", source_text_unit_id="c1")]

    with patch(
        "app.knowledge_layer.ingestion.relation_extractor.gateway.complete",
        new=AsyncMock(),
    ) as complete:
        relations = await RelationExtractor().extract([chunk], entities, entities, "ws-1")

    assert relations == []
    complete.assert_not_awaited()
