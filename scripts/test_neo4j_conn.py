"""测试 Neo4j 连接是否正常。"""
import asyncio
from neo4j import AsyncGraphDatabase


async def main():
    driver = AsyncGraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", "neo4jpassword"),
    )
    async with driver.session(database="neo4j") as session:
        result = await session.run("RETURN 1 AS val")
        record = await result.single()
        print(f"Neo4j 连接成功: {record['val']}")
    await driver.close()


asyncio.run(main())
