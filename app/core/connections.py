"""基础设施连接管理 — 统一管理 PostgreSQL/Redis/MinIO/Neo4j 连接生命周期。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("prd2tsd.connections")


@dataclass
class ConnHealth:
    """连接健康状态。"""

    name: str
    connected: bool
    enabled: bool
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseConnector:
    """连接器抽象基类。"""

    def __init__(self, name: str, enabled: bool = False) -> None:
        """初始化连接器。

        Args:
            name: 连接器名称。
            enabled: 是否启用（已连接）。
        """
        self.name = name
        self.enabled = enabled
        self._connected = False

    async def connect(self) -> bool:
        """建立连接。子类必须实现。

        Returns:
            是否连接成功。
        """
        raise NotImplementedError

    async def disconnect(self) -> None:
        """断开连接。子类必须实现。"""
        raise NotImplementedError

    def is_connected(self) -> bool:
        """检查连接状态。

        Returns:
            是否已连接。
        """
        return self._connected

    async def health(self) -> ConnHealth:
        """返回健康状态。子类应覆盖以实现具体检测。

        Returns:
            连接健康状态。
        """
        return ConnHealth(
            name=self.name,
            connected=self._connected,
            enabled=self.enabled,
        )


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
            # 测试连接
            async with self._engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
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
                    await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
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


class MinIOConnector(BaseConnector):
    """MinIO 连接器（预留，块 D/E 启用）。"""

    def __init__(
        self,
        endpoint: str = "",
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "",
        secure: bool = False,
    ) -> None:
        """初始化 MinIO 连接器。

        Args:
            endpoint: MinIO 端点。
            access_key: 访问密钥。
            secret_key: 秘密密钥。
            bucket: 默认桶名。
            secure: 是否使用 HTTPS。
        """
        super().__init__(name="minio", enabled=False)
        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.bucket = bucket or settings.MINIO_BUCKET
        self.secure = secure or settings.MINIO_SECURE
        self._client = None

    async def connect(self) -> bool:
        """建立 MinIO 连接。

        Returns:
            是否连接成功。
        """
        try:
            from minio import Minio

            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            # 测试连接
            self._client.list_buckets()
            # 确保桶存在
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
            self._connected = True
            self.enabled = True
            logger.info("MinIO 连接成功: %s", self.endpoint)
            return True
        except Exception as e:
            self._connected = False
            logger.error("MinIO 连接失败: %s", str(e))
            return False

    async def disconnect(self) -> None:
        """断开 MinIO 连接。"""
        self._client = None
        self._connected = False
        self.enabled = False
        logger.info("MinIO 连接已关闭")

    def get_client(self) -> Any:
        """获取 MinIO 客户端。

        Returns:
            Minio 客户端实例。

        Raises:
            RuntimeError: 连接器未初始化时抛出。
        """
        if not self._client or not self._connected:
            raise RuntimeError("MinIO 连接器未初始化")
        return self._client

    async def health(self) -> ConnHealth:
        """检查 MinIO 健康状态。

        Returns:
            连接健康状态。
        """
        if not self.enabled:
            return ConnHealth(name=self.name, connected=False, enabled=False, error="lazy init")
        start = time.monotonic()
        try:
            if self._client:
                self._client.list_buckets()
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


class Neo4jConnector(BaseConnector):
    """Neo4j 连接器（预留，块 B 启用）。"""

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
        super().__init__(name="neo4j", enabled=False)
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


class ConnectionManager:
    """连接管理器 — 统一管理所有外部服务连接的生命周期。"""

    def __init__(self) -> None:
        """初始化连接管理器。"""
        self._connectors: dict[str, BaseConnector] = {}
        self._lifetime: str = "init"

    def register(self, name: str, connector: BaseConnector) -> None:
        """注册连接器。

        Args:
            name: 连接器名称。
            connector: 连接器实例。
        """
        self._connectors[name] = connector
        logger.info("连接器已注册: %s", name)

    def get(self, name: str) -> BaseConnector:
        """获取连接器。

        Args:
            name: 连接器名称。

        Returns:
            连接器实例。

        Raises:
            KeyError: 连接器未注册时抛出。
        """
        if name not in self._connectors:
            raise KeyError(f"连接器未注册: {name}")
        return self._connectors[name]

    async def startup(self) -> None:
        """启动所有活跃连接。"""
        self._lifetime = "started"
        for name, connector in self._connectors.items():
            if connector.enabled:
                logger.info("正在连接: %s", name)
                await connector.connect()
            else:
                logger.info("跳过连接（lazy init）: %s", name)

    async def shutdown(self) -> None:
        """按依赖顺序优雅关闭所有连接。

        关闭顺序：Neo4j → MinIO → Redis → PostgreSQL
        """
        self._lifetime = "stopped"
        shutdown_order = ["neo4j", "minio", "redis", "postgres"]
        for name in shutdown_order:
            if name in self._connectors:
                connector = self._connectors[name]
                if connector.is_connected():
                    logger.info("正在关闭: %s", name)
                    await connector.disconnect()

    async def health_check(self) -> dict[str, Any]:
        """批量检查所有连接状态。

        Returns:
            {连接名: 健康状态} 字典。
        """
        result: dict[str, Any] = {}
        for name, connector in self._connectors.items():
            health = await connector.health()
            result[name] = {
                "connected": health.connected,
                "enabled": health.enabled,
                "latency_ms": health.latency_ms,
                "error": health.error,
            }
        return result

    def is_healthy(self, name: str) -> bool:
        """查询某连接的健康状态。

        Args:
            name: 连接器名称。

        Returns:
            是否健康（已连接且启用）。
        """
        if name not in self._connectors:
            return False
        connector = self._connectors[name]
        return connector.enabled and connector.is_connected()


# 全局单例
connection_manager = ConnectionManager()


def init_connections() -> ConnectionManager:
    """初始化并注册所有连接器。

    Returns:
        配置好的 ConnectionManager 实例。
    """
    mgr = connection_manager

    # PostgreSQL — 块 A 启用
    mgr.register("postgres", PostgreSQLConnector())

    # Redis — 块 A 注册但不连接（lazy init）
    mgr.register("redis", RedisConnector())

    # MinIO — 块 A 注册但不连接（lazy init）
    mgr.register("minio", MinIOConnector())

    # Neo4j — 块 A 注册但不连接（lazy init）
    mgr.register("neo4j", Neo4jConnector())

    return mgr
