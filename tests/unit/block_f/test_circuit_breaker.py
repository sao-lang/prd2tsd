"""Circuit Breaker 单元测试。"""

from __future__ import annotations

import pytest

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerManager,
    CircuitState,
)


class TestCircuitBreaker:
    """Circuit Breaker 测试。"""

    @pytest.mark.asyncio
    async def test_closed_state_initially(self):
        """测试初始状态为 CLOSED。"""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available is True

    @pytest.mark.asyncio
    async def test_successful_call_resets(self):
        """测试成功调用保持 CLOSED。"""
        cb = CircuitBreaker(name="test", failure_threshold=3)

        async def success():
            return "ok"

        result = await cb.call(success)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_failure_threshold_triggers_open(self):
        """测试连续失败达到阈值后熔断。"""
        cb = CircuitBreaker(name="test", failure_threshold=3)

        async def fail():
            raise ValueError("test error")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail)

        assert cb.state == CircuitState.OPEN
        assert cb.is_available is False
        assert cb.failure_count == 3

    @pytest.mark.asyncio
    async def test_open_state_rejects_calls(self):
        """测试熔断后直接拒绝调用。"""
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=9999)

        async def fail():
            raise ValueError("test error")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail)

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerError):
            await cb.call(fail)

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """测试超时后进入半开状态。"""
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1)

        async def fail():
            raise ValueError("test error")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail)

        assert cb.state == CircuitState.OPEN

        # 等待超时
        import asyncio
        await asyncio.sleep(0.15)

        async def success():
            return "recovered"

        result = await cb.call(success)
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_max_requests(self):
        """测试半开时限制请求数。"""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_requests=1,
        )

        async def fail():
            raise ValueError("test error")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail)

        import asyncio
        await asyncio.sleep(0.15)

        # 第一个请求允许（半开状态）
        with pytest.raises(ValueError):
            await cb.call(fail)

        # 第二个请求被拒绝
        with pytest.raises(CircuitBreakerError):
            await cb.call(fail)

    def test_to_dict(self):
        """测试 to_dict 输出。"""
        cb = CircuitBreaker(name="test")
        d = cb.to_dict()
        assert d["name"] == "test"
        assert d["state"] == "closed"
        assert d["is_available"] is True
        assert d["failure_count"] == 0

    def test_reset(self):
        """测试手动重置。"""
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.failure_count = 1
        cb.state = CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_circuit_breaker_manager(self):
        """测试 CircuitBreakerManager 注册/查询/重置。"""
        before = len(CircuitBreakerManager.get_all_status())
        cb1 = CircuitBreaker(name="cb1")
        cb2 = CircuitBreaker(name="cb2")
        CircuitBreakerManager.register(cb1)
        CircuitBreakerManager.register(cb2)

        assert CircuitBreakerManager.get("cb1") is cb1
        assert CircuitBreakerManager.get("cb2") is cb2
        assert len(CircuitBreakerManager.get_all_status()) == before + 2

        CircuitBreakerManager.reset_all()
        assert cb1.is_available is True

    @pytest.mark.asyncio
    async def test_success_after_half_open_closes(self):
        """测试半开状态下成功调用后恢复 CLOSED。"""
        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.1)

        async def fail():
            raise ValueError("error")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail)

        import asyncio
        await asyncio.sleep(0.15)

        # 用成功函数验证半开→关闭恢复
        async def ok():
            return "success"

        result = await cb.call(ok)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
