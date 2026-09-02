"""PGVectorStore SQL 与租户隔离单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.knowledge_layer.models import Chunk
from app.knowledge_layer.vector_store import PGVectorStore


class _RowsResult:
    """提供 SQLAlchemy Result 所需的最小 fetchall 接口。"""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def fetchall(self) -> list[SimpleNamespace]:
        """返回模拟查询行。"""
        return self._rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("table", "row", "expected_fragment"),
    [
        (
            "text_unit_embeddings",
            {"id": "t1", "text_content": "正文", "document_id": "d1", "similarity": 0.9},
            "text AS text_content, document_id",
        ),
        (
            "entity_embeddings",
            {"id": "e1", "text_content": "实体", "name": "实体", "entity_type": "Concept", "similarity": 0.8},
            "COALESCE(NULLIF(description, ''), name) AS text_content",
        ),
        (
            "claim_embeddings",
            {"id": "c1", "text_content": "断言", "subject": "主题", "claim_type": "decision", "similarity": 0.7},
            "content AS text_content, subject, claim_type",
        ),
    ],
)
async def test_similarity_search_selects_only_columns_from_target_table(
    table: str,
    row: dict[str, object],
    expected_fragment: str,
) -> None:
    """每种向量表应使用自身存在的列，并统一映射为 ScoredDoc。"""
    session = AsyncMock()
    session.execute.return_value = _RowsResult([SimpleNamespace(_mapping=row)])
    store = PGVectorStore(session=session)

    docs = await store.similarity_search([0.1, 0.2], table=table, workspace_id="ws-1")

    statement = str(session.execute.await_args.args[0])
    assert expected_fragment in statement
    assert "embedding IS NOT NULL" in statement
    assert "NULLS LAST" in statement
    assert docs[0].text == row["text_content"]
    assert session.execute.await_args.args[1]["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_upsert_chunk_writes_and_updates_workspace_id() -> None:
    """Chunk 新增和冲突更新都必须携带显式 workspace_id。"""
    session = AsyncMock()
    store = PGVectorStore(session=session)

    await store.upsert_chunk(
        Chunk(id="chunk-1", text="正文"),
        [0.1, 0.2],
        document_id="doc-1",
        workspace_id="ws-1",
    )

    statement = str(session.execute.await_args.args[0])
    params = session.execute.await_args.args[1]
    assert "workspace_id = EXCLUDED.workspace_id" in statement
    assert params["workspace_id"] == "ws-1"
    assert params["document_id"] == "doc-1"


@pytest.mark.asyncio
async def test_ensure_extensions_has_valid_document_id_default() -> None:
    """运行时建表 SQL 的 document_id 默认值必须闭合。"""
    session = AsyncMock()
    store = PGVectorStore(session=session)

    await store.ensure_extensions()

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    assert any("document_id VARCHAR(64) DEFAULT ''" in statement for statement in statements)
