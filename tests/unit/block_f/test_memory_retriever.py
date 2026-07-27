"""记忆检索器单元测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.session_history.memory_retriever import MemoryRetriever


class TestMemoryRetriever:
    """记忆检索器单元测试。"""

    @pytest.fixture
    def retriever(self) -> MemoryRetriever:
        return MemoryRetriever()

    @pytest.fixture
    def sample_messages(self) -> list[dict[str, str]]:
        return [
            {"role": "user", "content": "你好，我需要设计一个订单系统"},
            {"role": "assistant", "content": "好的，请告诉我具体需求"},
            {"role": "user", "content": "支持微信支付和支付宝"},
            {"role": "assistant", "content": "已记录支付需求，需要对接哪些接口？"},
            {"role": "user", "content": "先对接微信支付吧"},
        ]

    def test_recency_score_high_for_recent(self) -> None:
        """验证最近消息的时效性评分高。"""
        recent = datetime.now(UTC)
        score = MemoryRetriever._score_recency(recent)
        assert score > 0.9

    def test_recency_score_low_for_old(self) -> None:
        """验证旧消息的时效性评分低。"""
        old = datetime.now(UTC) - timedelta(days=7)
        score = MemoryRetriever._score_recency(old)
        assert score < 0.5

    @pytest.mark.asyncio
    async def test_retrieve_recency_strategy(
        self, retriever: MemoryRetriever, sample_messages: list[dict[str, str]],
    ) -> None:
        """验证 recency 策略返回最新消息优先。"""
        items = await retriever.retrieve(
            query="支付",
            messages=sample_messages,
            strategy="recency",
            top_k=10,
        )
        assert len(items) > 0
        # recency 策略下，所有消息都有 > 0 的 recency_score
        assert all(item.recency_score > 0 for item in items)
        # 内容都与样本消息匹配
        contents = [item.content for item in items]
        assert "先对接微信支付吧" in contents

    @pytest.mark.asyncio
    async def test_retrieve_hybrid_strategy(
        self, retriever: MemoryRetriever, sample_messages: list[dict[str, str]],
    ) -> None:
        """验证 hybrid 策略正常返回。"""
        items = await retriever.retrieve(
            query="支付",
            messages=sample_messages,
            strategy="hybrid",
            top_k=3,
        )
        assert len(items) <= 3
        assert all(item.composite_score > 0 for item in items)

    @pytest.mark.asyncio
    async def test_retrieve_top_k(
        self, retriever: MemoryRetriever, sample_messages: list[dict[str, str]],
    ) -> None:
        """验证 top_k 限制生效。"""
        items = await retriever.retrieve(
            query="test",
            messages=sample_messages,
            strategy="recency",
            top_k=2,
        )
        assert len(items) <= 2

    @pytest.mark.asyncio
    async def test_relevance_score_with_keyword(
        self, retriever: MemoryRetriever,
    ) -> None:
        """验证关键词重叠的相关性评分。"""
        score = await retriever._score_relevance("微信 支付", "支持 微信 支付 和 支付宝")
        assert score > 0

    @pytest.mark.asyncio
    async def test_relevance_score_no_match(self, retriever: MemoryRetriever) -> None:
        """验证无关键词匹配时得分为 0。"""
        score = await retriever._score_relevance("人工智能", "今天天气真好")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_importance_score_with_gateway(self) -> None:
        """验证 LLM 重要性评分。"""
        mock_gateway = MagicMock()
        mock_gateway.complete = AsyncMock(
            return_value=MagicMock(content="0.8")
        )
        retriever = MemoryRetriever(llm_gateway=mock_gateway)
        score = await retriever._score_importance("系统必须使用 PostgreSQL")
        assert score == 0.8

    @pytest.mark.asyncio
    async def test_importance_score_without_gateway(
        self, retriever: MemoryRetriever,
    ) -> None:
        """验证无 LLM 时返回默认重要性分数。"""
        score = await retriever._score_importance("闲聊内容")
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_compute_composite_hybrid(
        self, retriever: MemoryRetriever,
    ) -> None:
        """验证 hybrid 综合评分计算。"""
        # 直接测试静态方法
        from contracts.models import MemoryItem
        item = MemoryItem(
            content="test",
            role="user",
            recency_score=1.0,
            relevance_score=0.5,
            importance_score=0.0,
        )
        # hybrid weights: recency=0.3, relevance=0.4, importance=0.3
        score = MemoryRetriever._compute_composite(item, "hybrid")
        expected = 1.0 * 0.3 + 0.5 * 0.4 + 0.0 * 0.3
        assert abs(score - expected) < 0.001
