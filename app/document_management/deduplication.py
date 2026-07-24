"""文档去重 — SHA-256 文件哈希去重。"""

from __future__ import annotations

import hashlib

from app.core.logger import get_logger

logger = get_logger("prd2tsd.document_dedup")


class DocumentDeduplicator:
    """文档去重器。

    通过 SHA-256 文件哈希检测重复上传。
    """

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """计算文件内容的 SHA-256 哈希。

        Args:
            content: 文件字节数据。

        Returns:
            十六进制哈希字符串。
        """
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def is_duplicate(
        existing_hash: str | None,
        new_hash: str,
    ) -> bool:
        """判断是否为重复文件。

        Args:
            existing_hash: 已存在的文件哈希。
            new_hash: 新文件的哈希。

        Returns:
            是否为重复。
        """
        if not existing_hash:
            return False
        return existing_hash == new_hash
