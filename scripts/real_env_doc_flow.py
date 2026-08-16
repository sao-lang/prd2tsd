"""真实环境文档流验证（R10a）— 真实 PostgreSQL + MinIO。

覆盖：
1. DocumentManagementService.upload — 真实文件上传 → PG 记录 + MinIO 存储
2. UrlDocumentService.ingest — 真实 URL 抓取（依赖外网）→ URL 文档入库
3. 验证 file_type / source_url / 存储内容

运行：python scripts/real_env_doc_flow.py
（需外部服务运行；设置 MINIO_ENDPOINT=localhost:9000 供宿主机访问）
"""

from __future__ import annotations

import asyncio


async def main() -> None:
    """执行真实环境文档流验证。"""
    # 1. 初始化真实连接（PG/MinIO/Neo4j/Redis）
    from app.core.connections import connection_manager, init_connections

    init_connections()
    await connection_manager.startup()
    # MinIO 为 lazy init（enabled=False），显式连接
    minio_connector = connection_manager.get("minio")
    await minio_connector.connect()

    # 2. 获取真实 PG 会话
    connector = connection_manager.get("postgres")
    session = connector.get_session()

    # 3. 确定 workspace / user（FK 约束），不存在则创建
    from sqlalchemy import select, text

    ws_result = await session.execute(
        select(text("id")).select_from(text("workspaces")).limit(1),
    )
    ws_row = ws_result.first()
    if ws_row:
        workspace_id = ws_row[0]
        print(f"[workspace] 使用已有: {workspace_id}")
    else:
        import uuid
        from datetime import UTC, datetime

        workspace_id = str(uuid.uuid4())
        await session.execute(
            text(
                "INSERT INTO workspaces (id, name, created_at, updated_at) "
                "VALUES (:id, :name, :now, :now)"
            ),
            {"id": workspace_id, "name": "real-env-test", "now": datetime.now(UTC)},
        )
        await session.commit()
        print(f"[workspace] 已创建: {workspace_id}")

    user_result = await session.execute(
        select(text("id")).select_from(text("users")).limit(1),
    )
    user_row = user_result.first()
    user_id = user_row[0] if user_row else "real-env-user"
    print(f"[user] 使用: {user_id}")

    # 4. 真实文件上传（B3）
    from app.document_management.service import DocumentManagementService

    svc = DocumentManagementService()
    md_content = "# 真实环境测试文档\n\n这是一个用于验证上传链路的 Markdown 文档。".encode()
    upload = await svc.upload(
        session, workspace_id, user_id, md_content, "real-env-test.md",
    )
    print(
        f"[upload] doc_id={upload.document.id} file_type={upload.document.file_type} "
        f"status={upload.document.processing_status} dedup={upload.deduplicated}",
    )
    await session.commit()

    # 5. 验证 MinIO 中确实存了内容（DocumentOut 不含 storage_path，从 DB 模型读取）
    from sqlalchemy import select

    from app.document_management.storage import DocumentStorage
    from app.models.block_e import UploadedDocument

    db_result = await session.execute(
        select(UploadedDocument).where(UploadedDocument.id == upload.document.id),
    )
    db_doc = db_result.scalar_one()
    stored = await DocumentStorage().download(db_doc.storage_path)
    print(f"[minio] 存储校验: {len(stored)} bytes, 内容一致={stored == md_content}")

    # 6. 真实 URL 抓取入库（B2，依赖外网）
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://example.com")
            internet_ok = r.status_code == 200
    except Exception:
        internet_ok = False
    print(f"[internet] example.com 可达: {internet_ok}")

    if internet_ok:
        from app.web_indexing.url_document import UrlDocumentService

        url_svc = UrlDocumentService()
        url_upload = await url_svc.ingest(
            session, workspace_id, user_id, "https://example.com",
        )
        await session.commit()
        print(
            f"[url-ingest] doc_id={url_upload.document.id} "
            f"file_type={url_upload.document.file_type} "
            f"source_url={url_upload.document.source_url}",
        )
    else:
        print("[url-ingest] 跳过（无外网）")

    await session.close()
    print("[done] 真实环境文档流验证完成")


if __name__ == "__main__":
    asyncio.run(main())
