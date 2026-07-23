"""检查数据库表。"""
import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/prd2tsd")
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"
    )
    print(f"表数量: {len(rows)}")
    for r in rows:
        print(f"  - {r['table_name']}")
    await conn.close()


asyncio.run(main())
