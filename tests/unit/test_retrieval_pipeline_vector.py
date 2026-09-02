"""RetrievalPipeline 的 PGVector 多路融合单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.models import ScoredDoc
from app.knowledge_layer.pipeline import RetrievalPipeline


def _doc(doc_id: str, source: str, score: float = 1.0) -> ScoredDoc:
    """构造检索候选。"""
    return ScoredDoc(id=doc_id, text=f"{source} {doc_id}", score=score, source=source)


def _make_pipeline() -> tuple[RetrievalPipeline, AsyncMock, AsyncMock]:
    """构造隔离外部依赖的检索管线。"""
    graph_store = MagicMock()
    vector_store = AsyncMock()
    query_embedder = AsyncMock()
    query_embedder.embed_text.return_value = [0.1, 0.2]

    pipeline = RetrievalPipeline(
        graph_store=graph_store,
        vector_store=vector_store,
        query_embedder=query_embedder,
    )
    pipeline.rewriter = AsyncMock()
    pipeline.rewriter.rewrite.return_value = ["原查询", "改写查询"]
    pipeline.enricher = AsyncMock()
    pipeline.enricher.enrich.return_value = ("原查询", [])
    pipeline.local_search = AsyncMock()
    pipeline.local_search.search_as_docs.side_effect = [
        [_doc("graph-1", "local")],
        [_doc("graph-1", "local"), _doc("graph-2", "local", 0.8)],
    ]
    pipeline.reflection = AsyncMock()
    pipeline.reflection.judge.return_value = SimpleNamespace(
        judgment="accept",
        reason="结果充分",
        refined_query="",
    )
    pipeline.reranker = MagicMock()
    pipeline.reranker.rerank.side_effect = lambda _query, docs, top_k: docs[:top_k]
    pipeline.compressor = MagicMock()
    pipeline.compressor.compress.side_effect = lambda docs: docs
    return pipeline, vector_store, query_embedder


@pytest.mark.asyncio
async def test_local_mode_fuses_graph_and_pgvector_results() -> None:
    """Local 模式应以 RRF 融合 Neo4j 与 PGVector TextUnit 排名。"""
    pipeline, vector_store, query_embedder = _make_pipeline()
    vector_store.similarity_search.side_effect = [
        [_doc("vector-1", "vector", 0.95)],
        [_doc("vector-1", "vector", 0.9), _doc("vector-2", "vector", 0.8)],
    ]

    context = await pipeline.retrieve("原查询", mode="local", top_k=10, workspace_id="ws-1")

    assert {doc.id for doc in context.results} == {"graph-1", "graph-2", "vector-1", "vector-2"}
    assert query_embedder.embed_text.await_count == 2
    assert vector_store.similarity_search.await_count == 2
    for call in vector_store.similarity_search.await_args_list:
        assert call.kwargs["table"] == "text_unit_embeddings"
        assert call.kwargs["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_hybrid_mode_fuses_graph_vector_and_global_results() -> None:
    """Hybrid 模式应同时融合图、向量和 Global 三路排名。"""
    pipeline, vector_store, _ = _make_pipeline()
    pipeline.intent_router = MagicMock()
    pipeline.intent_router.route.return_value = "hybrid"
    vector_store.similarity_search.side_effect = [
        [_doc("vector-1", "vector")],
        [],
    ]
    pipeline.global_search = AsyncMock()
    pipeline.global_search.search.return_value = SimpleNamespace(answer="全局概述")
    pipeline.global_search.search_as_docs.return_value = [_doc("global-1", "global")]

    context = await pipeline.retrieve("原查询", mode="hybrid", top_k=10, workspace_id="ws-1")

    assert {doc.id for doc in context.results} == {"graph-1", "graph-2", "vector-1", "global-1"}
    assert context.global_summary == "全局概述"


@pytest.mark.asyncio
async def test_pgvector_failure_degrades_to_graph_results() -> None:
    """PGVector 异常不得中断主链路，应保留 Neo4j Local 结果。"""
    pipeline, vector_store, _ = _make_pipeline()
    vector_store.similarity_search.side_effect = RuntimeError("postgres unavailable")

    context = await pipeline.retrieve("原查询", mode="local", top_k=10, workspace_id="ws-1")

    assert [doc.id for doc in context.results] == ["graph-1", "graph-2"]


@pytest.mark.asyncio
async def test_zero_query_embedding_skips_pgvector_search() -> None:
    """Embedding 完全不可用时应跳过无意义的零向量查询。"""
    pipeline, vector_store, query_embedder = _make_pipeline()
    query_embedder.embed_text.return_value = [0.0, 0.0]

    context = await pipeline.retrieve("原查询", mode="local", top_k=10, workspace_id="ws-1")

    assert [doc.id for doc in context.results] == ["graph-1", "graph-2"]
    vector_store.similarity_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_reflection_refinement_requeries_pgvector() -> None:
    """反思产生 refined_query 后，PGVector 应使用新查询重新检索。"""
    pipeline, vector_store, query_embedder = _make_pipeline()
    pipeline.rewriter.rewrite.return_value = ["原查询"]
    pipeline.local_search.search_as_docs.side_effect = [
        [_doc("graph-1", "local")],
        [_doc("graph-2", "local")],
    ]
    vector_store.similarity_search.side_effect = [
        [_doc("vector-1", "vector")],
        [_doc("vector-2", "vector")],
    ]
    pipeline.reflection.judge.side_effect = [
        SimpleNamespace(
            judgment="refine",
            reason="召回不足",
            refined_query="精炼查询",
        ),
        SimpleNamespace(
            judgment="accept",
            reason="结果充分",
            refined_query="",
        ),
    ]

    context = await pipeline.retrieve("原查询", mode="local", top_k=10, workspace_id="ws-1")

    assert [call.args[0] for call in query_embedder.embed_text.await_args_list] == ["原查询", "精炼查询"]
    assert {doc.id for doc in context.results} == {"graph-2", "vector-2"}
