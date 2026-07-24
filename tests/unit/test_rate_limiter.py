"""速率限制器单元测试。"""

from __future__ import annotations

import pytest

from app.llm_gateway.rate_limiter import RateLimiter


@pytest.fixture
def limiter() -> RateLimiter:
    """创建干净的速率限制器。"""
    return RateLimiter(default_rpm=10, default_tpm=10000)


@pytest.mark.asyncio
async def test_rate_limiter_allows_first_request(limiter: RateLimiter) -> None:
    """验证首次请求被允许。"""
    result = await limiter.check("ws-1")
    assert result["allowed"] is True


@pytest.mark.asyncio
async def test_rate_limiter_rpm_exceeded(limiter: RateLimiter) -> None:
    """验证 RPM 超限时拒绝。"""
    # 填满窗口（10 次请求）
    for _ in range(10):
        await limiter.record("ws-2")
    result = await limiter.check("ws-2")
    assert result["allowed"] is False
    assert result["remaining_rpm"] == 0


@pytest.mark.asyncio
async def test_rate_limiter_tpm_exceeded(limiter: RateLimiter) -> None:
    """验证 TPM 超限时拒绝。"""
    # 消耗 9500 tokens（接近 10000 上限）
    await limiter.record("ws-3", 9500)
    result = await limiter.check("ws-3", 1000)
    assert result["allowed"] is False


@pytest.mark.asyncio
async def test_rate_limiter_custom_limit(limiter: RateLimiter) -> None:
    """验证自定义限制覆盖默认值。"""
    limiter.set_limit("ws-4", rpm=5, tpm=5000)
    for _ in range(5):
        await limiter.record("ws-4")
    result = await limiter.check("ws-4")
    assert result["allowed"] is False
    assert result["remaining_rpm"] == 0


@pytest.mark.asyncio
async def test_rate_limiter_reset(limiter: RateLimiter) -> None:
    """验证重置后恢复。"""
    for _ in range(10):
        await limiter.record("ws-5")
    result = await limiter.check("ws-5")
    assert result["allowed"] is False
    limiter.reset("ws-5")
    result = await limiter.check("ws-5")
    assert result["allowed"] is True
