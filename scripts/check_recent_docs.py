"""查询真实 PG 中最近上传的文档记录（验证 file_type/source_url 实际状态）。"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.connections import connection_manager, init_connections
from app.models.block_e import UploadedDocument


async def main() -> None:
    """查询最近 5 条文档记录。"""
    init_connections()
    await connection_manager.startup()
    connector = connection_manager.get("postgres")
    session = connector.get_session()
    try:
        result = await session.execute(
            select(UploadedDocument).order_by(UploadedDocument.created_at.desc()).limit(5),
        )
        for doc in result.scalars():
            print(
                f"id={doc.id[:8]} file_type={doc.file_type} "
                f"source_url={doc.source_url} status={doc.processing_status} "
                f"filename={doc.original_filename[:30]}",
            )
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
