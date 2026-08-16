"""通用熔断器（Circuit Breaker）— 装饰器式熔断保护。

状态机：CLOSED → (连续失败 N 次) → OPEN → (等待超时) → HALF_OPEN
        → (试探成功) → CLOSED
        → (试探失败) → OPEN

使用场景：LLM 调用、外部 API 调用、数据库查询等。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from app.core.logger import get_logger

logger = get_logger("prd2tsd.circuit_breaker")

P = ParamSpec("P")
R = TypeVar("R")


class CircuitState(StrEnum):
    """熔断器状态枚举。"""

    CLOSED = "closed"  # 正常工作
    OPEN = "open"  # 熔断
    HALF_OPEN = "half_open"  # 半开（试探恢复）


class CircuitBreakerError(Exception):
    """熔断器打开异常。"""

    def __init__(self, name: str, state: CircuitState) -> None:
        self.name = name
        self.state = state
        super().__init__(f"CircuitBreaker '{name}' 已打开 (state={state.value})")


class CircuitBreaker:
    """通用熔断器 — 可装饰任何异步函数。

    状态机：CLOSED → (连续失败 N 次) → OPEN → (等待超时) → HALF_OPEN
            → (试探成功) → CLOSED
            → (试探失败) → OPEN
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_requests: int = 1,
    ) -> None:
        """初始化熔断器。

        Args:
            name: 熔断器名称（用于日志和指标）。
            failure_threshold: 连续失败多少次后熔断。
            recovery_timeout: 熔断后等待多少秒进入半开状态。
            half_open_max_requests: 半开时允许的最大试探请求数。
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_requests = 0
        self._lock = asyncio.Lock()

    async def call(
        self,
        fn: Callable[P, Awaitable[R]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        """执行被熔断保护的异步函数。

        Args:
            fn: 异步函数。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            函数执行结果。

        Raises:
            CircuitBreakerError: 熔断器打开时抛出。
        """
        async with self._lock:
            # 检查当前状态
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_requests = 0
                    logger.info("熔断器 %s 进入半开状态", self.name)
                else:
                    raise CircuitBreakerError(self.name, self.state)

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_requests >= self.half_open_max_requests:
                    raise CircuitBreakerError(self.name, self.state)
                self.half_open_requests += 1

        # 执行函数
        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """成功回调 — 重置为 CLOSED。"""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_requests = 0
            logger.info("熔断器 %s 恢复为关闭状态", self.name)

    async def _on_failure(self) -> None:
        """失败回调 — 累计失败次数，阈值到达时熔断。"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    "熔断器 %s 已打开（连续失败 %d/%d）",
                    self.name,
                    self.failure_count,
                    self.failure_threshold,
                )

    @property
    def is_available(self) -> bool:
        """当前是否可用（用于查询）。"""
        return self.state != CircuitState.OPEN

    def reset(self) -> None:
        """手动重置熔断器。"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_requests = 0
        logger.info("熔断器 %s 已手动重置", self.name)

    def to_dict(self) -> dict[str, Any]:
        """导出状态（用于 Prometheus 指标和 API 查询）。"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "is_available": self.is_available,
        }


def with_circuit_breaker(
    name: str | None = None,
    failure_threshold: int = 3,
    recovery_timeout: float = 30.0,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """熔断器装饰器。

    Args:
        name: 熔断器名称（默认使用函数名）。
        failure_threshold: 熔断阈值。
        recovery_timeout: 恢复超时。

    Usage:
        @with_circuit_breaker(name="deepseek-api")
        async def call_deepseek(prompt: str) -> str:
            ...
    """

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        """装饰器：为函数绑定独立熔断器。"""
        cb = CircuitBreaker(
            name=name or fn.__name__,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """执行被装饰函数并经过熔断器保护。"""
            return await cb.call(fn, *args, **kwargs)

        wrapper.circuit_breaker = cb  # type: ignore[attr-defined]
        return wrapper

    return decorator


class CircuitBreakerManager:
    """熔断器管理器 — 统一注册/查询/监控。"""

    _breakers: dict[str, CircuitBreaker] = {}

    @classmethod
    def register(cls, breaker: CircuitBreaker) -> None:
        """注册熔断器。"""
        cls._breakers[breaker.name] = breaker

    @classmethod
    def get(cls, name: str) -> CircuitBreaker | None:
        """获取熔断器。"""
        return cls._breakers.get(name)

    @classmethod
    def get_all_status(cls) -> list[dict[str, Any]]:
        """获取所有熔断器状态。"""
        return [cb.to_dict() for cb in cls._breakers.values()]

    @classmethod
    def reset_all(cls) -> None:
        """手动重置所有熔断器。"""
        for cb in cls._breakers.values():
            cb.reset()
