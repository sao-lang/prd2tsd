"""持久化语义缓存的相似度、隔离与过期测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.llm_gateway.cache import MemorySemanticCacheStore, SemanticCache


async def _embedding_loader(text: str) -> tuple[list[float], str]:
    """返回可预测的测试向量。"""
    if "database" in text.lower() or "数据库" in text:
        return [1.0, 0.01], "test-embedding"
    return [0.0, 1.0], "test-embedding"


@pytest.mark.asyncio
async def test_semantically_similar_prompt_hits_persistent_cache() -> None:
    """不同文本但高余弦相似度时应命中持久化缓存。"""
    store = MemorySemanticCacheStore()
    cache = SemanticCache(store=store, similarity_threshold=0.95, enabled=True)
    await cache.store(
        prompt="Which database should we choose?",
        response="Use PostgreSQL",
        task_type="analysis",
        workspace_id="ws-a",
        model="model-a",
        embedding_loader=_embedding_loader,
    )

    result = await cache.lookup(
        prompt="数据库如何选型？",
        task_type="analysis",
        workspace_id="ws-a",
        model="model-a",
        embedding_loader=_embedding_loader,
    )

    assert result == "Use PostgreSQL"


@pytest.mark.asyncio
async def test_semantic_cache_isolated_by_workspace_task_and_model() -> None:
    """语义相似也不得跨租户、任务或模型复用。"""
    store = MemorySemanticCacheStore()
    cache = SemanticCache(store=store, enabled=True)
    await cache.store(
        prompt="database selection",
        response="private response",
        task_type="analysis",
        workspace_id="ws-a",
        model="model-a",
        embedding_loader=_embedding_loader,
    )

    result = await cache.lookup(
        prompt="数据库选型",
        task_type="analysis",
        workspace_id="ws-b",
        model="model-a",
        embedding_loader=_embedding_loader,
    )

    assert result is None


@pytest.mark.asyncio
async def test_expired_semantic_entry_is_not_returned() -> None:
    """过期的持久化向量条目不得参与匹配。"""
    store = MemorySemanticCacheStore()
    cache = SemanticCache(store=store, enabled=True)
    await cache.store(
        prompt="database selection",
        response="stale response",
        task_type="analysis",
        workspace_id="ws-a",
        model="model-a",
        embedding_loader=_embedding_loader,
    )
    store.entries[0]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    cache.clear()

    result = await cache.lookup(
        prompt="数据库选型",
        task_type="analysis",
        workspace_id="ws-a",
        model="model-a",
        embedding_loader=_embedding_loader,
    )

    assert result is None


@pytest.mark.asyncio
async def test_semantic_matching_requires_workspace_scope() -> None:
    """缺少 workspace_id 时只允许进程内精确缓存，不持久化相似度条目。"""
    store = MemorySemanticCacheStore()
    cache = SemanticCache(store=store, enabled=True)

    await cache.store(
        prompt="database selection",
        response="private response",
        task_type="analysis",
        workspace_id="",
        model="model-a",
        embedding_loader=_embedding_loader,
    )
    result = await cache.lookup(
        prompt="数据库选型",
        task_type="analysis",
        workspace_id="",
        model="model-a",
        embedding_loader=_embedding_loader,
    )

    assert result is None
    assert store.entries == []
