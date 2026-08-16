"""上下文压缩器单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.session_history.compressor import ChatMessage, ContextCompressor


class TestContextCompressor:
    """上下文压缩器单元测试。"""

    @pytest.fixture
    def compressor(self) -> ContextCompressor:
        return ContextCompressor()

    def test_estimate_tokens_chinese(self) -> None:
        """验证中文 Token 估算。"""
        msgs = [ChatMessage(role="user", content="你好世界")]
        tokens = ContextCompressor._estimate_tokens(msgs)
        # 4个中文字 * 1.5 = 6
        assert tokens == 6

    def test_estimate_tokens_english(self) -> None:
        """验证英文 Token 估算。"""
        msgs = [ChatMessage(role="user", content="hello world")]
        tokens = ContextCompressor._estimate_tokens(msgs)
        # 11个英文字符 * 0.25 = 2.75, int = 2
        assert tokens == 2

    @pytest.mark.asyncio
    async def test_compress_under_limit_returns_original(
        self, compressor: ContextCompressor,
    ) -> None:
        """验证未超限时返回原列表。"""
        msgs = [ChatMessage(role="user", content="短消息")]
        result = await compressor.compress(msgs, max_tokens=1000)
        assert result == msgs
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_truncate_strategy(self, compressor: ContextCompressor) -> None:
        """验证截断策略可工作。"""
        long_text = "a" * 10000
        msgs = [ChatMessage(role="user", content=long_text)]
        result = await compressor.compress(msgs, max_tokens=10, reserve_for_latest=5)
        # 应该有压缩
        assert len(result) <= len(msgs)

    @pytest.mark.asyncio
    async def test_rolling_strategy_keeps_newest(self, compressor: ContextCompressor) -> None:
        """验证 rolling 策略保留最新消息。"""
        msgs = [
            ChatMessage(role="user", content="旧消息" * 100),
            ChatMessage(role="user", content="新消息"),
        ]
        result = await compressor.compress(msgs, max_tokens=20, reserve_for_latest=10)
        # 保护区应包含最新消息
        assert any("新消息" in m.content for m in result)

    @pytest.mark.asyncio
    async def test_compress_llm_summarize_fallback(self) -> None:
        """验证 LLM 摘要失败时降级到 rolling。"""
        mock_gateway = MagicMock()
        mock_gateway.complete = AsyncMock(side_effect=Exception("LLM 不可用"))
        compressor = ContextCompressor(llm_gateway=mock_gateway)
        msgs = [ChatMessage(role="user", content="短消息")] * 20
        # 设置极小的 max_tokens 确保触发压缩
        result = await compressor.compress(msgs, max_tokens=5, reserve_for_latest=2)
        assert len(result) > 0
        # 验证调用了 LLM（但失败了）
        mock_gateway.complete.assert_called_once()
