"""MinIO 连接器。"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.connections.base import BaseConnector, ConnHealth
from app.core.logger import get_logger

logger = get_logger("prd2tsd.connections")


class MinIOConnector(BaseConnector):
    """MinIO 连接器（预留，块 D/E 启用）。"""

    def __init__(
        self,
        endpoint: str = "",
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "",
        secure: bool = False,
    ) -> None:
        """初始化 MinIO 连接器。

        Args:
            endpoint: MinIO 端点。
            access_key: 访问密钥。
            secret_key: 秘密密钥。
            bucket: 默认桶名。
            secure: 是否使用 HTTPS。
        """
        super().__init__(name="minio", enabled=False)
        self.endpoint = endpoint or settings.MINIO_ENDPOINT
        self.access_key = access_key or settings.MINIO_ACCESS_KEY
        self.secret_key = secret_key or settings.MINIO_SECRET_KEY
        self.bucket = bucket or settings.MINIO_BUCKET
        self.secure = secure or settings.MINIO_SECURE
        self._client = None

    async def connect(self) -> bool:
        """建立 MinIO 连接。

        Returns:
            是否连接成功。
        """
        try:
            from minio import Minio

            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            self._client.list_buckets()
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
            self._connected = True
            self.enabled = True
            logger.info("MinIO 连接成功: %s", self.endpoint)
            return True
        except Exception as e:
            self._connected = False
            logger.error("MinIO 连接失败: %s", str(e))
            return False

    async def disconnect(self) -> None:
        """断开 MinIO 连接。"""
        self._client = None
        self._connected = False
        self.enabled = False
        logger.info("MinIO 连接已关闭")

    def get_client(self) -> Any:
        """获取 MinIO 客户端。

        Returns:
            Minio 客户端实例。

        Raises:
            RuntimeError: 连接器未初始化时抛出。
        """
        if not self._client or not self._connected:
            raise RuntimeError("MinIO 连接器未初始化")
        return self._client

    async def health(self) -> ConnHealth:
        """检查 MinIO 健康状态。

        Returns:
            连接健康状态。
        """
        if not self.enabled:
            return ConnHealth(name=self.name, connected=False, enabled=False, error="lazy init")
        start = time.monotonic()
        try:
            if self._client:
                self._client.list_buckets()
                latency = (time.monotonic() - start) * 1000
                return ConnHealth(
                    name=self.name,
                    connected=True,
                    enabled=self.enabled,
                    latency_ms=round(latency, 2),
                )
            return ConnHealth(name=self.name, connected=False, enabled=self.enabled, error="客户端未初始化")
        except Exception as e:
            return ConnHealth(name=self.name, connected=False, enabled=self.enabled, error=str(e))
