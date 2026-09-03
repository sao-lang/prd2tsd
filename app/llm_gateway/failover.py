"""Provider Failover 路由选择器。

Failover 只维护按优先级排列的候选目标，并读取 CircuitBreaker 状态。
失败计数、OPEN/HALF_OPEN/CLOSED 转换和恢复试探全部由 CircuitBreaker 负责。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerManager
from app.core.logger import get_logger

logger = get_logger("prd2tsd.failover")

BreakerResolver = Callable[[str], CircuitBreaker | None]


class AllProvidersUnavailableError(Exception):
    """所有 Provider 均不可用异常。"""

    def __init__(self, model_type: str) -> None:
        self.model_type = model_type
        super().__init__(f"所有 {model_type} Provider 均不可用")


@dataclass(frozen=True)
class FailoverTarget:
    """不可变的 Failover 路由目标，不保存运行时健康状态。"""

    provider: str
    model: str
    priority: int  # 0=primary, 1=fallback, 2=ultimate
    model_type: str = "llm"


class FailoverManager:
    """维护 Failover 链，并只读查询 Provider 熔断状态。"""

    def __init__(self, breaker_resolver: BreakerResolver | None = None) -> None:
        self._chains: dict[str, list[FailoverTarget]] = {}
        self._breaker_resolver = breaker_resolver or self._default_breaker_resolver

    @staticmethod
    def _default_breaker_resolver(provider: str) -> CircuitBreaker | None:
        """按 Gateway 的统一命名规则查询 Provider 熔断器。"""
        return CircuitBreakerManager.get(f"provider:{provider}")

    def configure(self, model_type: str, chain: list[FailoverTarget]) -> None:
        """配置 Failover 链；目标始终按优先级保存。"""
        self._chains[model_type] = sorted(chain, key=lambda target: target.priority)
        logger.info(
            "Failover 链已配置: %s → %s",
            model_type,
            [f"{target.provider}:{target.model}" for target in self._chains[model_type]],
        )

    def get_chain(self, model_type: str) -> list[FailoverTarget]:
        """返回路由链副本，不暴露内部列表。"""
        return list(self._chains.get(model_type, []))

    def get_available_targets(self, model_type: str) -> list[FailoverTarget]:
        """按优先级返回熔断器当前允许尝试的目标。

        未注册熔断器的动态 Provider 视为可尝试，最终调用前由 Gateway 创建熔断器。
        此方法不改变熔断器或 Failover 自身状态。
        """
        available: list[FailoverTarget] = []
        for target in self._chains.get(model_type, []):
            breaker = self._breaker_resolver(target.provider)
            if breaker is None or breaker.is_available:
                available.append(target)
        return available

    async def get_target(self, model_type: str) -> FailoverTarget:
        """返回最高优先级的可用目标，保留原异步接口兼容性。"""
        targets = self.get_available_targets(model_type)
        if not targets:
            raise AllProvidersUnavailableError(model_type)
        return targets[0]

    def get_chain_status(self, model_type: str) -> list[dict[str, Any]]:
        """返回合并了只读 CircuitBreaker 快照的路由状态。"""
        statuses: list[dict[str, Any]] = []
        for target in self._chains.get(model_type, []):
            breaker = self._breaker_resolver(target.provider)
            statuses.append(
                {
                    "provider": target.provider,
                    "model": target.model,
                    "priority": target.priority,
                    "circuit_state": breaker.state.value if breaker else "unregistered",
                    "failure_count": breaker.failure_count if breaker else 0,
                    "is_available": breaker.is_available if breaker else True,
                }
            )
        return statuses
