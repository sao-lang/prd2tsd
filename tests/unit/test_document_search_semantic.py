"""文档语义搜索回归测试（2026-08-16 条目 31）。

覆盖：
- _semantic_search：向量命中 → 按 document_id 聚合最高分 → 组装 SearchResult
- search()：语义路失败时降级仅 FTS（不阻断主流程）
- _merge_results：FTS 与语义按 document_id 去重、取高分、排序
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.document_management.models import SearchResult
from app.document_management.search import DocumentSearchService
from app.knowledge_layer.models import ScoredDoc


class _FakeVectorStore:
    """返回固定向量块结果的桩。"""

    def __init__(self, docs: list[ScoredDoc]) -> None:
        self._docs = docs

    async def similarity_search(self, embedding, table, top_k, workspace_id):
        return self._docs


async def _fake_embed(texts, task_type):
    return SimpleNamespace(embeddings=[[0.1, 0.2, 0.3]])


class _FakeDb:
    """最小 DB 桩：_semantic_search 只依赖 execute + scalars。"""

    def __init__(self, docs: list[SimpleNamespace]) -> None:
        self._docs = docs

    async def execute(self, stmt):
        return self

    def scalars(self):
        return self

    def all(self):
        return self._docs


def _make_doc(doc_id: str, score: float, title: str = "文档") -> ScoredDoc:
    return ScoredDoc(
        id=f"chunk-{doc_id}",
        text=f"{title} 内容",
        score=score,
        source="vector",
        metadata={"table": "text_unit_embeddings", "document_id": doc_id},
    )


def _make_uploaded(doc_id: str, title: str = "文档") -> SimpleNamespace:
    return SimpleNamespace(
        id=doc_id,
        title=title,
        description=None,
        file_type="pdf",
        file_size=1024,
        created_at=None,
    )


@pytest.mark.asyncio
async def test_semantic_search_aggregates_by_document(monkeypatch) -> None:
    """同一文档多个 chunk 取最高分，跨文档按分排序。"""
    monkeypatch.setattr(
        "app.llm_gateway.gateway.embed",
        _fake_embed,
    )
    service = DocumentSearchService(
        vector_store=_FakeVectorStore(
            [
                _make_doc("doc-a", 0.91, "订单"),
                _make_doc("doc-a", 0.87, "订单"),
                _make_doc("doc-b", 0.95, "用户"),
            ]
        )
    )
    db = _FakeDb([_make_uploaded("doc-a", "订单"), _make_uploaded("doc-b", "用户")])
    results = await service._semantic_search(db, "ws-1", "订单怎么设计", limit=5)

    assert [r.document_id for r in results] == ["doc-b", "doc-a"]
    assert results[1].score == 0.91  # doc-a 取最高 chunk 分
    assert all(r.match_type == "semantic" for r in results)


@pytest.mark.asyncio
async def test_search_falls_back_to_fts_when_semantic_fails(monkeypatch) -> None:
    """语义路抛异常时降级仅 FTS，不阻断搜索。"""
    service = DocumentSearchService()

    async def _broken_semantic(db, workspace_id, query, limit):
        raise RuntimeError("embedding 服务不可用")

    async def _fake_fts(db, workspace_id, query, page, page_size):
        return [SearchResult(document_id="doc-1", title="架构", file_type="md", file_size=10)]

    monkeypatch.setattr(service, "_semantic_search", _broken_semantic)
    monkeypatch.setattr(service, "_fts_search", _fake_fts)
    results = await service.search(db=None, workspace_id="ws-1", query="架构")  # type: ignore[arg-type]
    assert len(results) == 1
    assert results[0].document_id == "doc-1"


def test_merge_results_dedupes_and_keeps_higher_score() -> None:
    """FTS 与语义命中同一文档时保留高分，按分排序。"""
    fts = [
        SearchResult(document_id="doc-1", title="A", file_type="md", file_size=1, score=0.5, match_type="fts"),
        SearchResult(document_id="doc-2", title="B", file_type="md", file_size=2, score=0.4, match_type="fts"),
    ]
    semantic = [
        SearchResult(document_id="doc-1", title="A", file_type="md", file_size=1, score=0.9, match_type="semantic"),
    ]
    merged = DocumentSearchService._merge_results(fts, semantic, limit=5)

    assert [r.document_id for r in merged] == ["doc-1", "doc-2"]
    assert merged[0].match_type == "semantic"
    assert merged[0].score == 0.9
