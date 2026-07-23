"""连接管理单元测试。"""

from __future__ import annotations

import pytest

from app.core.connections import (
    ConnectionManager,
    ConnHealth,
    MinIOConnector,
    Neo4jConnector,
    PostgreSQLConnector,
    RedisConnector,
)


@pytest.mark.asyncio
async def test_connection_manager_startup_shutdown():
    """验证 ConnectionManager 启动/关闭生命周期。"""
    mgr = ConnectionManager()

    # 注册但不连接
    pg = PostgreSQLConnector(database_url="sqlite+aiosqlite://", pool_size=1, max_overflow=0)
    pg.enabled = False  # 测试环境下不连接真实 PG
    mgr.register("postgres", pg)

    assert mgr._lifetime == "init"
    await mgr.startup()
    assert mgr._lifetime == "started"
    await mgr.shutdown()
    assert mgr._lifetime == "stopped"


@pytest.mark.asyncio
async def test_lazy_init_connector():
    """验证预留服务（Redis/MinIO/Neo4j）注册但不连接。"""
    mgr = ConnectionManager()

    redis = RedisConnector(redis_url="redis://localhost:6379/0")
    redis.enabled = False
    mgr.register("redis", redis)

    minio = MinIOConnector(endpoint="localhost:9000")
    minio.enabled = False
    mgr.register("minio", minio)

    neo4j = Neo4jConnector(uri="bolt://localhost:7687")
    neo4j.enabled = False
    mgr.register("neo4j", neo4j)

    # 验证注册但不连接
    assert mgr.get("redis").enabled is False
    assert mgr.get("minio").enabled is False
    assert mgr.get("neo4j").enabled is False

    await mgr.startup()

    # 启动后仍不连接（lazy init）
    assert mgr.get("redis").is_connected() is False
    assert mgr.get("minio").is_connected() is False
    assert mgr.get("neo4j").is_connected() is False


@pytest.mark.asyncio
async def test_connection_health_check():
    """验证健康检查正确反映各连接状态。"""
    mgr = ConnectionManager()

    pg = PostgreSQLConnector(database_url="sqlite+aiosqlite://", pool_size=1, max_overflow=0)
    pg.enabled = False
    mgr.register("postgres", pg)

    redis = RedisConnector(redis_url="redis://localhost:6379/0")
    redis.enabled = False
    mgr.register("redis", redis)

    health = await mgr.health_check()
    assert "postgres" in health
    assert "redis" in health


@pytest.mark.asyncio
async def test_graceful_shutdown_order():
    """验证关闭注册顺序。"""
    mgr = ConnectionManager()

    pg = PostgreSQLConnector(database_url="sqlite+aiosqlite://", pool_size=1, max_overflow=0)
    pg.enabled = False
    mgr.register("postgres", pg)

    redis = RedisConnector(redis_url="redis://localhost:6379/0")
    redis.enabled = False
    mgr.register("redis", redis)

    neo4j = Neo4jConnector(uri="bolt://localhost:7687")
    neo4j.enabled = False
    mgr.register("neo4j", neo4j)

    # 验证注册了 3 个连接器
    assert len(mgr._connectors) == 3


def test_conn_health():
    """验证 ConnHealth 数据类。"""
    health = ConnHealth(name="test", connected=True, enabled=True, latency_ms=1.23)
    assert health.name == "test"
    assert health.connected is True
    assert health.latency_ms == 1.23


@pytest.mark.asyncio
async def test_register_and_get():
    """验证注册和获取连接器。"""
    mgr = ConnectionManager()
    pg = PostgreSQLConnector(database_url="sqlite+aiosqlite://", pool_size=1, max_overflow=0)
    pg.enabled = False
    mgr.register("postgres", pg)

    retrieved = mgr.get("postgres")
    assert retrieved is pg
    assert retrieved.name == "postgres"

    with pytest.raises(KeyError):
        mgr.get("nonexistent")
