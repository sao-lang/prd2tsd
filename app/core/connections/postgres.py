"""PostgreSQL 连接器 — 基于 asyncpg + SQLAlchemy async engine。"""

from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.connections.base import BaseConnector, ConnHealth
from app.core.logger import get_logger

logger = get_logger("prd2tsd.connections")


class PostgreSQLConnector(BaseConnector):
    """PostgreSQL 连接器 — 基于 asyncpg + SQLAlchemy async engine。"""

    def __init__(
        self,
        database_url: str = "",
        pool_size: int = 10,
        max_overflow: int = 20,
    ) -> None:
        """初始化 PostgreSQL 连接器。

        Args:
            database_url: 数据库 URL。
            pool_size: 连接池大小。
            max_overflow: 最大溢出连接数。
        """
        super().__init__(name="postgres", enabled=True)
        self.database_url = database_url or settings.DATABASE_URL
        self.pool_size = pool_size or settings.DATABASE_POOL_SIZE
        self.max_overflow = max_overflow or settings.DATABASE_MAX_OVERFLOW
        self._engine = None
        self._session_factory = None

    async def connect(self) -> bool:
        """建立 PostgreSQL 连接池。

        Returns:
            是否连接成功。
        """
        try:
            self._engine = create_async_engine(
                self.database_url,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                echo=False,
            )
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self._session_factory = async_sessionmaker(
                self._engine, class_=AsyncSession, expire_on_commit=False
            )
            self._connected = True
            logger.info("PostgreSQL 连接成功: %s", self.database_url)
            return True
        except Exception as e:
            self._connected = False
            logger.error("PostgreSQL 连接失败: %s", str(e))
            return False

    async def disconnect(self) -> None:
        """断开 PostgreSQL 连接池。"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._connected = False
            logger.info("PostgreSQL 连接已关闭")

    def get_session(self) -> AsyncSession:
        """获取异步数据库会话。

        Returns:
            AsyncSession 实例。

        Raises:
            RuntimeError: 连接器未初始化时抛出。
        """
        if not self._session_factory or not self._connected:
            raise RuntimeError("PostgreSQL 连接器未初始化")
        return self._session_factory()

    async def health(self) -> ConnHealth:
        """检查 PostgreSQL 健康状态。

        Returns:
            连接健康状态。
        """
        start = time.monotonic()
        try:
            if self._engine:
                async with self._engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                latency = (time.monotonic() - start) * 1000
                return ConnHealth(
                    name=self.name,
                    connected=True,
                    enabled=self.enabled,
                    latency_ms=round(latency, 2),
                )
            return ConnHealth(
                name=self.name,
                connected=False,
                enabled=self.enabled,
                error="引擎未初始化",
            )
        except Exception as e:
            return ConnHealth(
                name=self.name,
                connected=False,
                enabled=self.enabled,
                error=str(e),
            )
