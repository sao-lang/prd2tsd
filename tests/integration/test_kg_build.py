"""集成测试 — 知识图谱构建。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.models import KGEntity
from app.knowledge_layer.pipeline import KnowledgeGraphBuilder


@pytest.mark.asyncio
async def test_build_from_markdown(tmp_path) -> None:
    """用样本 .md 模拟构建知识图谱（所有外部依赖 Mock）。"""
    md_file = tmp_path / "test_sample.md"
    md_file.write_text(
        "# 用户服务\n\n用户服务使用 Spring Boot 框架，基于 PostgreSQL 数据库。\n",
        encoding="utf-8",
    )

    # Mock 存储
    mock_graph = MagicMock()
    mock_graph.get_all_entities = AsyncMock(return_value=[])
    mock_graph.upsert_entities = AsyncMock(return_value=[])

    mock_vector = MagicMock()
    mock_vector.ensure_extensions = AsyncMock()
    mock_vector.upsert_chunk = AsyncMock()
    mock_vector.upsert_entity_embedding = AsyncMock()

    builder = KnowledgeGraphBuilder(
        graph_store=mock_graph,
        vector_store=mock_vector,
    )
    builder.entity_extractor.extract = AsyncMock(
        return_value=[
            KGEntity(id="e1", name="Spring Boot", type="TechStack", category="框架",
                     description="Java 框架"),
            KGEntity(id="e2", name="PostgreSQL", type="TechStack", category="数据库",
                     description="关系型数据库"),
        ]
    )
    builder.entity_embedder.embed_entity = MagicMock(return_value=[0.1] * 1024)
    builder.entity_embedder.embed_text = MagicMock(return_value=[0.1] * 1024)

    stats = await builder.build_from_document(str(md_file))

    assert stats.entities >= 2
    assert stats.chunks >= 1
    assert stats.file_path == str(md_file)


@pytest.mark.asyncio
async def test_build_empty_file(tmp_path) -> None:
    """验证空文件构建。"""
    md_file = tmp_path / "empty.md"
    md_file.write_text("", encoding="utf-8")

    mock_graph = MagicMock()
    mock_graph.get_all_entities = AsyncMock(return_value=[])
    mock_graph.upsert_entities = AsyncMock(return_value=[])

    mock_vector = MagicMock()
    mock_vector.ensure_extensions = AsyncMock()

    builder = KnowledgeGraphBuilder(graph_store=mock_graph, vector_store=mock_vector)
    builder.entity_extractor.extract = AsyncMock(return_value=[])
    builder.entity_embedder.embed_text = MagicMock(return_value=[0.1] * 1024)

    stats = await builder.build_from_document(str(md_file))
    assert stats.entities == 0
    assert stats.chunks == 0
