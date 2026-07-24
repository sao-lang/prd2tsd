"""文档存储后端 — MinIO 对象存储。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from app.core.connections import connection_manager
from app.core.logger import get_logger

logger = get_logger("prd2tsd.document_storage")


class DocumentStorage:
    """文档存储后端。

    基于 MinIO 的对象存储，路径格式：
    `prd-docs/{workspace_id}/{yyyy}/{mm}/{file_hash}{ext}`
    """

    def __init__(self) -> None:
        """初始化文档存储。"""
        self._client: Any = None

    def _get_client(self) -> Any:
        """获取 MinIO 客户端。

        Returns:
            MinIO 客户端实例。

        Raises:
            RuntimeError: MinIO 不可用时抛出。
        """
        if self._client is None:
            connector = connection_manager.get("minio")
            self._client = connector.get_client()
        return self._client

    def _build_path(
        self,
        workspace_id: str,
        file_hash: str,
        ext: str,
    ) -> str:
        """构建存储路径。

        Args:
            workspace_id: 工作空间 ID。
            file_hash: 文件哈希。
            ext: 文件扩展名（含.）。

        Returns:
            存储路径。
        """
        now = datetime.now(UTC)
        return f"prd-docs/{workspace_id}/{now.year}/{now.month:02d}/{file_hash}{ext}"

    async def upload(
        self,
        workspace_id: str,
        content: bytes,
        filename: str,
    ) -> dict[str, Any]:
        """上传文件到 MinIO。

        注意：MinIO 客户端为同步实现，通过 asyncio.to_thread 避免阻塞事件循环。

        Args:
            workspace_id: 工作空间 ID。
            content: 文件字节数据。
            filename: 原始文件名。

        Returns:
            包含 storage_path, file_hash, file_size 的字典。
        """
        import asyncio

        file_hash = hashlib.sha256(content).hexdigest()
        ext = _get_ext(filename)
        storage_path = self._build_path(workspace_id, file_hash, ext)

        client = self._get_client()
        bucket = "prd-docs"

        # 确保 bucket 存在（同步操作扔到线程池）
        if not await asyncio.to_thread(client.bucket_exists, bucket):
            await asyncio.to_thread(client.make_bucket, bucket)
            logger.info("创建桶: %s", bucket)

        content_length = len(content)
        content_stream = BytesIO(content)
        content_type = _guess_mime(ext)

        await asyncio.to_thread(
            client.put_object,
            bucket,
            storage_path,
            content_stream,
            content_length,
            content_type=content_type,
        )

        logger.info(
            "文件已上传: %s (%s, %d bytes)", storage_path, file_hash[:12], content_length,
        )
        return {
            "storage_path": storage_path,
            "file_hash": file_hash,
            "file_size": content_length,
        }

    async def download(self, storage_path: str) -> bytes:
        """从 MinIO 下载文件。

        Args:
            storage_path: 存储路径。

        Returns:
            文件字节数据。
        """
        client = self._get_client()
        response = client.get_object("prd-docs", storage_path)
        data = response.read()
        response.close()
        response.release_conn()
        return data

    async def delete(self, storage_path: str) -> bool:
        """从 MinIO 删除文件。

        Args:
            storage_path: 存储路径。

        Returns:
            是否删除成功。
        """
        try:
            client = self._get_client()
            client.remove_object("prd-docs", storage_path)
            logger.info("文件已删除: %s", storage_path)
            return True
        except Exception as exc:
            logger.warning("删除文件失败: %s - %s", storage_path, exc)
            return False

    async def get_presigned_url(self, storage_path: str, expires: int = 3600) -> str:
        """获取预签名 URL。

        Args:
            storage_path: 存储路径。
            expires: 过期时间（秒）。

        Returns:
            预签名 URL。
        """
        client = self._get_client()
        return client.presigned_get_object("prd-docs", storage_path, expires=expires)


def _get_ext(filename: str) -> str:
    """从文件名获取扩展名。

    Args:
        filename: 文件名。

    Returns:
        扩展名（含.）。
    """
    idx = filename.rfind(".")
    return filename[idx:].lower() if idx >= 0 else ".bin"


def _guess_mime(ext: str) -> str:
    """根据扩展名猜测 MIME 类型。

    Args:
        ext: 文件扩展名。

    Returns:
        MIME 类型。
    """
    mapping = {
        ".md": "text/markdown",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".tsv": "text/tab-separated-values",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
    }
    return mapping.get(ext, "application/octet-stream")
