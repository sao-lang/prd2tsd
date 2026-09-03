"""FailoverManager 单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from app.core.circuit_breaker import CircuitBreaker
from app.llm_gateway.failover import AllProvidersUnavailableError, FailoverManager, FailoverTarget


class TestFailoverManager:
    """验证 Failover 只读取熔断状态，不维护第二套健康状态。"""

    def setup_method(self) -> None:
        self.breakers = {
            "deepseek": CircuitBreaker("provider:deepseek", failure_threshold=1),
            "openai": CircuitBreaker("provider:openai", failure_threshold=1),
        }
        self.manager = FailoverManager(self.breakers.get)

    def _configure(self) -> None:
        self.manager.configure(
            "llm",
            [
                FailoverTarget(provider="openai", model="gpt-4o-mini", priority=1),
                FailoverTarget(provider="deepseek", model="deepseek-chat", priority=0),
            ],
        )

    def test_configure_sorts_chain_without_health_state(self) -> None:
        """链只保存不可变路由元数据并按优先级排序。"""
        self._configure()

        chain = self.manager.get_chain("llm")

        assert [target.provider for target in chain] == ["deepseek", "openai"]
        assert not hasattr(chain[0], "healthy")

    @pytest.mark.asyncio
    async def test_get_target_reads_closed_breaker(self) -> None:
        """CLOSED 状态下选择最高优先级目标且不发 ping。"""
        self._configure()

        target = await self.manager.get_target("llm")

        assert target.provider == "deepseek"
        assert self.breakers["deepseek"].failure_count == 0

    @pytest.mark.asyncio
    async def test_open_primary_is_skipped_without_mutation(self) -> None:
        """OPEN Primary 被跳过，Failover 不修改其失败计数。"""
        self._configure()

        async def fail() -> None:
            raise RuntimeError("provider unavailable")

        with pytest.raises(RuntimeError):
            await self.breakers["deepseek"].call(fail)
        before = self.breakers["deepseek"].failure_count

        targets = self.manager.get_available_targets("llm")

        assert [target.provider for target in targets] == ["openai"]
        assert self.breakers["deepseek"].failure_count == before == 1

    @pytest.mark.asyncio
    async def test_recovery_window_makes_primary_eligible_again(self) -> None:
        """恢复窗口到期由熔断器重新放行 Primary，Failover 自动优先选择它。"""
        self.breakers["deepseek"] = CircuitBreaker(
            "provider:deepseek",
            failure_threshold=1,
            recovery_timeout=0.01,
        )
        self._configure()

        async def fail() -> None:
            raise RuntimeError("temporary failure")

        with pytest.raises(RuntimeError):
            await self.breakers["deepseek"].call(fail)
        await asyncio.sleep(0.02)

        target = await self.manager.get_target("llm")

        assert target.provider == "deepseek"
        assert self.breakers["deepseek"].failure_count == 1

    @pytest.mark.asyncio
    async def test_all_open_raises(self) -> None:
        """所有熔断器 OPEN 时返回统一不可用错误。"""
        self._configure()

        async def fail() -> None:
            raise RuntimeError("down")

        for breaker in self.breakers.values():
            with pytest.raises(RuntimeError):
                await breaker.call(fail)

        with pytest.raises(AllProvidersUnavailableError):
            await self.manager.get_target("llm")

    def test_status_is_circuit_breaker_snapshot(self) -> None:
        """状态输出来自熔断器，没有 Failover 私有健康字段。"""
        self._configure()

        status = self.manager.get_chain_status("llm")

        assert status[0]["circuit_state"] == "closed"
        assert status[0]["failure_count"] == 0
        assert status[0]["is_available"] is True
        assert "healthy" not in status[0]

    def test_unknown_model_type_raises_error(self) -> None:
        """未知路由无目标。"""
        with pytest.raises(AllProvidersUnavailableError):
            asyncio.run(self.manager.get_target("unknown"))
