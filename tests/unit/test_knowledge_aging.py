"""单元测试 — 知识老化策略。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.knowledge_layer.ingestion.knowledge_aging import KnowledgeAgingPolicy


class TestKnowledgeAging:
    """知识老化策略测试。"""

    @pytest.fixture
    def graph_store_mock(self) -> MagicMock:
        """创建 Mock 图存储。"""
        mock = MagicMock()
        mock.run_cypher = AsyncMock(return_value=[{"cnt": 2}])
        return mock

    async def test_apply_aging_returns_stats(self, graph_store_mock) -> None:
        """验证老化执行返回统计。"""
        policy = KnowledgeAgingPolicy(graph_store=graph_store_mock)
        stats = await policy.apply_aging()
        assert "downgraded" in stats
        assert "archived" in stats
        assert "deleted" in stats
        assert stats["downgraded"] >= 0

    async def test_aging_with_workspace(self, graph_store_mock) -> None:
        """验证指定工作空间的老化。"""
        policy = KnowledgeAgingPolicy(graph_store=graph_store_mock)
        stats = await policy.apply_aging(workspace_id="ws1")
        assert isinstance(stats["downgraded"], int)
