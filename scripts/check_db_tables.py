"""检查数据库中已有的表。"""

import asyncio

import asyncpg


async def main() -> None:
    """连接数据库并列出所有表。"""
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/prd2tsd")
    rows = await conn.fetch(
        "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'"
    )
    print("现有表:")
    for r in rows:
        print(f"  - {r['tablename']}")
    await conn.close()


asyncio.run(main())
