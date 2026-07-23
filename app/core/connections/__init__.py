"""基础设施连接管理 — 统一管理 PostgreSQL/Redis/MinIO/Neo4j 连接生命周期。"""

from __future__ import annotations

from typing import Any

from app.core.connections.base import BaseConnector, ConnHealth
from app.core.connections.minio import MinIOConnector
from app.core.connections.neo4j import Neo4jConnector
from app.core.connections.postgres import PostgreSQLConnector
from app.core.connections.redis import RedisConnector
from app.core.logger import get_logger

logger = get_logger("prd2tsd.connections")

__all__ = [
    "BaseConnector",
    "ConnHealth",
    "ConnectionManager",
    "PostgreSQLConnector",
    "RedisConnector",
    "MinIOConnector",
    "Neo4jConnector",
    "connection_manager",
    "init_connections",
]


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

    # Neo4j — 块 B 启用（启动时自动连接）
    mgr.register("neo4j", Neo4jConnector())

    return mgr
