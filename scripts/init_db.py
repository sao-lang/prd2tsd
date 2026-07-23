#!/usr/bin/env python3
"""数据库初始化脚本 — 创建所有表并插入初始数据。"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.organization import Organization
from app.models.role import Role


async def init_database() -> None:
    """初始化数据库。

    创建所有表并插入初始数据（系统角色等）。
    """
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/prd2tsd",
    )

    print(f"连接到数据库: {database_url}")
    engine = create_async_engine(database_url, echo=True)

    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 所有表已创建")

    # 创建会话
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # 检查是否需要插入初始数据
        result = await session.execute(text("SELECT COUNT(*) FROM roles"))
        count = result.scalar()

        if count == 0:
            # 创建默认系统角色（示例）
            print("插入初始数据...")

            # 创建默认组织（用于系统初始化）
            org = Organization(
                name="System",
                slug="system",
                plan="enterprise",
            )
            session.add(org)
            await session.flush()

            # 创建系统预置角色
            roles_data = [
                Role(
                    organization_id=org.id,
                    name="admin",
                    is_system=True,
                    permissions=[
                        "workspace:create", "workspace:read", "workspace:update",
                        "workspace:delete", "workspace:manage_members",
                        "prd:create", "prd:read", "prd:update", "prd:delete",
                        "model_config:read", "model_config:update",
                    ],
                ),
                Role(
                    organization_id=org.id,
                    name="editor",
                    is_system=True,
                    permissions=["workspace:read", "prd:create", "prd:read", "prd:update"],
                ),
                Role(
                    organization_id=org.id,
                    name="viewer",
                    is_system=True,
                    permissions=["workspace:read", "prd:read"],
                ),
            ]
            for role in roles_data:
                session.add(role)

            await session.commit()
            print("✅ 初始数据已插入")
        else:
            print("⏭️ 数据库中已有数据，跳过初始数据插入")

    await engine.dispose()
    print("✅ 数据库初始化完成")


if __name__ == "__main__":
    asyncio.run(init_database())
