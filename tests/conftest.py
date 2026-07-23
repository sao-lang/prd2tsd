"""pytest fixtures — 测试数据库和客户端。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.connections import ConnectionManager, PostgreSQLConnector
from app.models.base import Base


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环。"""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """创建测试数据库会话。

    使用内存 SQLite 或测试用 PostgreSQL。
    """
    # 尝试使用测试环境变量，默认使用 SQLite 内存数据库
    import os

    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite://",
    )

    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """创建测试 HTTP 客户端。"""
    # 导入并创建应用
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def connection_manager() -> ConnectionManager:
    """创建测试用连接管理器。"""
    mgr = ConnectionManager()
    # 注册但不连接（测试环境可能没有真实服务）
    mgr.register("postgres", PostgreSQLConnector(enabled=False))
    return mgr
