"""多格式知识图谱构建（Block E B3）单元测试 — build_from_bytes 链路。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.knowledge_layer.models import BuildStats
from app.knowledge_layer.pipeline import KnowledgeGraphBuilder


class TestBuildFromBytes:
    """KnowledgeGraphBuilder.build_from_bytes 链路测试（mock 内部依赖）。"""

    @pytest.mark.asyncio
    async def test_build_from_bytes_markdown(self) -> None:
        """验证 md 内容经提取后走 build_from_text 链路。"""
        builder = KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder)  # 绕过 __init__（避免连接 Neo4j/PGVector）
        builder.build_from_text = AsyncMock(return_value=BuildStats(entities=1, chunks=2))

        stats = await builder.build_from_bytes(
            "# 标题\n正文".encode(), "doc.md", workspace_id="ws-1",
        )

        builder.build_from_text.assert_awaited_once()
        args = builder.build_from_text.await_args
        assert args is not None
        assert "# 标题\n正文" in args.args[0]
        assert args.kwargs["source_name"] == "doc.md"
        assert args.kwargs["workspace_id"] == "ws-1"
        assert stats.entities == 1

    @pytest.mark.asyncio
    async def test_build_from_bytes_csv(self) -> None:
        """验证 csv 内容经行级转换后入图。"""
        builder = KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder)
        builder.build_from_text = AsyncMock(return_value=BuildStats(entities=0, chunks=0))

        await builder.build_from_bytes(b"a,b\n1,2\n", "data.csv", workspace_id="ws-1")

        args = builder.build_from_text.await_args
        assert args is not None
        assert "记录: a，b。" in args.args[0]

    @pytest.mark.asyncio
    async def test_build_from_bytes_empty_text_raises(self) -> None:
        """验证无可提取文本时抛错。"""
        builder = KnowledgeGraphBuilder.__new__(KnowledgeGraphBuilder)
        builder.build_from_text = AsyncMock(return_value=BuildStats(entities=0, chunks=0))

        with pytest.raises(ValueError, match="无可提取文本"):
            await builder.build_from_bytes(b"", "empty.md", workspace_id="ws-1")
        builder.build_from_text.assert_not_awaited()
