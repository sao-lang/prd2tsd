"""确保数据库表存在。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.base import Base


async def main():
    engine = create_async_engine("postgresql+asyncpg://postgres:postgres@localhost:5432/prd2tsd")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("ok")

asyncio.run(main())
