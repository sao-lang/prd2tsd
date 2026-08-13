"""外部服务真实连接 Smoke Test（R10a 强制）— 禁止 Mock。"""

from __future__ import annotations

import asyncio


async def smoke_postgres() -> None:
    """PostgreSQL 连通性。"""
    import asyncpg

    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/prd2tsd")
    version = await conn.fetchval("SELECT version()")
    tables = await conn.fetchval(
        "SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public'",
    )
    await conn.close()
    print(f"[PostgreSQL] OK - {version[:40]} | tables={tables}")


async def smoke_redis() -> None:
    """Redis 连通性。"""
    import redis

    r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=5)
    print(f"[Redis] OK - PING={r.ping()}")


async def smoke_minio() -> None:
    """MinIO 连通性。"""
    from minio import Minio

    client = Minio(
        "localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False,
    )
    exists = client.bucket_exists("prd2tsd")
    print(f"[MinIO] OK - server reachable, bucket 'prd2tsd' exists={exists}")


async def smoke_neo4j() -> None:
    """Neo4j 连通性（bolt 端口 7701）。"""
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7701",
        auth=("neo4j", "neo4jpassword"),
    )
    async with driver.session(database="neo4j") as session:
        record = await (await session.run("RETURN 1 AS v")).single()
        print(f"[Neo4j] OK - RETURN 1 = {record['v']}")
    await driver.close()


async def main() -> None:
    """按序执行全部冒烟检查。"""
    for name, fn in [
        ("postgres", smoke_postgres),
        ("redis", smoke_redis),
        ("minio", smoke_minio),
        ("neo4j", smoke_neo4j),
    ]:
        try:
            await fn()
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] FAIL - {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
