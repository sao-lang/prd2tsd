"""MemoryRetriever recency 修复回归测试 — 时间戳来自消息而非 now。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.session_history.memory_retriever import MemoryRetriever


@pytest.mark.asyncio
async def test_recency_uses_message_timestamp() -> None:
    """新旧消息时间戳不同 → recency 分数应不同。"""
    retriever = MemoryRetriever()
    now = datetime.now(UTC)
    messages = [
        {"role": "user", "content": "旧的讨论", "timestamp": (now - timedelta(days=3)).isoformat()},
        {"role": "user", "content": "刚刚的消息", "timestamp": now.isoformat()},
    ]
    results = await retriever.retrieve("讨论", messages, strategy="recency", top_k=2)

    assert results[0].recency_score > results[1].recency_score
