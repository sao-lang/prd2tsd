"""Provider Failover 管理器 — 配置驱动自动切换 Provider。

职责：
- 维护每个 model_type 的 Failover 链
- 定期健康检测（ping 每个 Provider）
- 调用失败时自动切到下一个
- 恢复后自动切回 Primary
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.core.logger import get_logger
from app.llm_gateway.config_manager import ModelConfigManager
from app.llm_gateway.providers import ProviderFactory

# 缓存实例，避免每次 _ping 重建
_config_manager = ModelConfigManager()
_provider_factory = ProviderFactory()

logger = get_logger("prd2tsd.failover")


class AllProvidersUnavailableError(Exception):
    """所有 Provider 均不可用异常。"""

    def __init__(self, model_type: str) -> None:
        self.model_type = model_type
        super().__init__(f"所有 {model_type} Provider 均不可用")


@dataclass
class FailoverTarget:
    """Failover 目标。"""

    provider: str
    model: str
    priority: int  # 0=primary, 1=fallback, 2=ultimate
    model_type: str = "llm"
    healthy: bool = True
    last_check: float = 0.0


class FailoverManager:
    """Failover 管理器 — 自动切换 Provider。

    维护每个 model_type 的 Failover 链，调用失败时自动切换到下一个健康目标。
    """

    def __init__(self) -> None:
        self._chains: dict[str, list[FailoverTarget]] = {}
        self._current_index: dict[str, int] = {}
        self._health_check_interval = 60.0  # 每 60 秒检测一次

    def configure(self, model_type: str, chain: list[FailoverTarget]) -> None:
        """配置 Failover 链。

        Args:
            model_type: 模型类型（如 "llm", "embedding"）。
            chain: 按优先级排序的 Failover 目标列表。
        """
        self._chains[model_type] = chain
        self._current_index[model_type] = 0
        logger.info(
            "Failover 链已配置: %s → %s",
            model_type,
            [f"{t.provider}:{t.model}" for t in chain],
        )

    async def get_target(self, model_type: str) -> FailoverTarget:
        """获取当前可用的目标。自动跳过不健康的。

        Args:
            model_type: 模型类型。

        Returns:
            可用的 FailoverTarget。

        Raises:
            AllProvidersUnavailableError: 所有 Provider 均不可用。
        """
        chain = self._chains.get(model_type, [])
        idx = self._current_index.get(model_type, 0)

        for offset, target in enumerate(chain[idx:], start=idx):
            if await self._is_healthy(target):
                self._current_index[model_type] = offset
                return target

        raise AllProvidersUnavailableError(model_type)

    async def record_failure(self, model_type: str, provider: str, model: str = "") -> None:
        """记录调用失败，自动切到下一个。

        Args:
            model_type: 模型类型。
            provider: Provider 名称。
        """
        chain = self._chains.get(model_type, [])
        for target in chain:
            if target.provider == provider and (not model or target.model == model):
                target.healthy = False
                logger.warning("Provider 标记为不可用: %s/%s", model_type, provider)
                break
        self._current_index[model_type] = 0  # 重置从头找

    def get_chain(self, model_type: str) -> list[FailoverTarget]:
        """返回按优先级排序的链副本，供 Gateway 执行动态路由。"""
        return sorted(self._chains.get(model_type, []), key=lambda target: target.priority)

    async def _is_healthy(self, target: FailoverTarget) -> bool:
        """检查目标是否健康（带缓存）。"""
        if not target.healthy:
            return False
        now = time.monotonic()
        if now - target.last_check > self._health_check_interval:
            target.healthy = await self._ping(target)
            target.last_check = now
        return target.healthy

    async def _ping(self, target: FailoverTarget) -> bool:
        """检测 Provider 是否可用（发一个最小请求）。"""
        try:
            config = _config_manager.get_config(target.model_type, target.provider)
            provider = _provider_factory.create(config.provider, config)
            await provider.complete(
                prompt="ping",
                model=target.model,
                max_tokens=1,
            )
            return True
        except Exception:
            return False

    def get_chain_status(self, model_type: str) -> list[dict[str, Any]]:
        """获取 Failover 链状态。"""
        chain = self._chains.get(model_type, [])
        return [
            {
                "provider": t.provider,
                "model": t.model,
                "priority": t.priority,
                "healthy": t.healthy,
            }
            for t in chain
        ]

    def reset_targets(self, model_type: str) -> None:
        """重置所有目标为健康状态。"""
        chain = self._chains.get(model_type, [])
        for t in chain:
            t.healthy = True
        self._current_index[model_type] = 0
        logger.info("Failover 链已重置: %s", model_type)
