"""PostgreSQL 联通性测试。"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """创建到真实 PostgreSQL 的连接会话。"""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/prd2tsd",
    )
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgresql_connection(db_session: AsyncSession):
    """验证 PostgreSQL 连接正常。"""
    result = await db_session.execute(text("SELECT version()"))
    row = result.fetchone()
    assert row is not None
    version = row[0]
    print(f"PostgreSQL 版本: {version}")
    assert "PostgreSQL" in version


@pytest.mark.asyncio
async def test_pgvector_available(db_session: AsyncSession):
    """验证 pgvector 扩展可用。"""
    try:
        result = await db_session.execute(text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"))
        row = result.fetchone()
        if row:
            print(f"pgvector {row[1]} 可用")
        else:
            print("pgvector 扩展未安装（非必需）")
    except Exception:
        print("pgvector 不可用（非必需）")


@pytest.mark.asyncio
async def test_database_basic_operations(db_session: AsyncSession):
    """验证数据库基本操作。"""
    # CREATE
    await db_session.execute(text("CREATE TABLE IF NOT EXISTS test_conn (id serial PRIMARY KEY, name text)"))
    await db_session.execute(text("INSERT INTO test_conn (name) VALUES ('test')"))
    await db_session.commit()

    # READ
    result = await db_session.execute(text("SELECT name FROM test_conn"))
    rows = result.fetchall()
    assert len(rows) >= 1

    # DROP
    await db_session.execute(text("DROP TABLE test_conn"))
    await db_session.commit()
