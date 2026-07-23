"""Redis 连接器。"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.connections.base import BaseConnector, ConnHealth
from app.core.logger import get_logger

logger = get_logger("prd2tsd.connections")


class RedisConnector(BaseConnector):
    """Redis 连接器（预留，块 B/C 启用）。"""

    def __init__(self, redis_url: str = "", pool_size: int = 10) -> None:
        """初始化 Redis 连接器。

        Args:
            redis_url: Redis URL。
            pool_size: 连接池大小。
        """
        super().__init__(name="redis", enabled=False)
        self.redis_url = redis_url or settings.REDIS_URL
        self.pool_size = pool_size or settings.REDIS_POOL_SIZE
        self._client = None

    async def connect(self) -> bool:
        """建立 Redis 连接。

        Returns:
            是否连接成功。
        """
        try:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=self.pool_size,
            )
            await self._client.ping()
            self._connected = True
            self.enabled = True
            logger.info("Redis 连接成功: %s", self.redis_url)
            return True
        except Exception as e:
            self._connected = False
            logger.error("Redis 连接失败: %s", str(e))
            return False

    async def disconnect(self) -> None:
        """断开 Redis 连接。"""
        if self._client:
            await self._client.close()
            self._client = None
            self._connected = False
            self.enabled = False
            logger.info("Redis 连接已关闭")

    def get_client(self) -> Any:
        """获取 Redis 客户端。

        Returns:
            Redis 客户端实例。

        Raises:
            RuntimeError: 连接器未初始化时抛出。
        """
        if not self._client or not self._connected:
            raise RuntimeError("Redis 连接器未初始化")
        return self._client

    async def health(self) -> ConnHealth:
        """检查 Redis 健康状态。

        Returns:
            连接健康状态。
        """
        if not self.enabled:
            return ConnHealth(name=self.name, connected=False, enabled=False, error="lazy init")
        start = time.monotonic()
        try:
            if self._client:
                await self._client.ping()
                latency = (time.monotonic() - start) * 1000
                return ConnHealth(
                    name=self.name,
                    connected=True,
                    enabled=self.enabled,
                    latency_ms=round(latency, 2),
                )
            return ConnHealth(name=self.name, connected=False, enabled=self.enabled, error="客户端未初始化")
        except Exception as e:
            return ConnHealth(name=self.name, connected=False, enabled=self.enabled, error=str(e))
