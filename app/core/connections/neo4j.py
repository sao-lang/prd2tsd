"""Neo4j 连接器。"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.connections.base import BaseConnector, ConnHealth
from app.core.logger import get_logger

logger = get_logger("prd2tsd.connections")


class Neo4jConnector(BaseConnector):
    """Neo4j 连接器。"""

    def __init__(
        self,
        uri: str = "",
        user: str = "",
        password: str = "",
        database: str = "",
    ) -> None:
        """初始化 Neo4j 连接器。

        Args:
            uri: Neo4j Bolt URI。
            user: 用户名。
            password: 密码。
            database: 数据库名。
        """
        super().__init__(name="neo4j", enabled=True)
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self.database = database or settings.NEO4J_DATABASE
        self._driver = None

    async def connect(self) -> bool:
        """建立 Neo4j 连接。

        Returns:
            是否连接成功。
        """
        try:
            from neo4j import AsyncGraphDatabase

            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            async with self._driver.session(database=self.database) as session:
                result = await session.run("RETURN 1 AS val")
                await result.single()
            self._connected = True
            self.enabled = True
            logger.info("Neo4j 连接成功: %s", self.uri)
            return True
        except Exception as e:
            self._connected = False
            logger.error("Neo4j 连接失败: %s", str(e))
            return False

    async def disconnect(self) -> None:
        """断开 Neo4j 连接。"""
        if self._driver:
            await self._driver.close()
            self._driver = None
            self._connected = False
            self.enabled = False
            logger.info("Neo4j 连接已关闭")

    def get_driver(self) -> Any:
        """获取 Neo4j 驱动。

        Returns:
            AsyncDriver 实例。

        Raises:
            RuntimeError: 连接器未初始化时抛出。
        """
        if not self._driver or not self._connected:
            raise RuntimeError("Neo4j 连接器未初始化")
        return self._driver

    async def health(self) -> ConnHealth:
        """检查 Neo4j 健康状态。

        Returns:
            连接健康状态。
        """
        if not self.enabled:
            return ConnHealth(name=self.name, connected=False, enabled=False, error="lazy init")
        start = time.monotonic()
        try:
            if self._driver:
                async with self._driver.session(database=self.database) as session:
                    result = await session.run("RETURN 1 AS val")
                    await result.single()
                latency = (time.monotonic() - start) * 1000
                return ConnHealth(
                    name=self.name,
                    connected=True,
                    enabled=self.enabled,
                    latency_ms=round(latency, 2),
                )
            return ConnHealth(name=self.name, connected=False, enabled=self.enabled, error="驱动未初始化")
        except Exception as e:
            return ConnHealth(name=self.name, connected=False, enabled=self.enabled, error=str(e))
