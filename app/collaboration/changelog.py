"""变更历史服务。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.collaboration.models import ChangeLogEntry
from app.core.logger import get_logger

logger = get_logger("prd2tsd.changelog")


class ChangeLogService:
    """变更历史服务。

    记录文档的所有变更操作：创建/更新/评论/建议/删除。
    注意：当前使用内存存储（self._entries），重启后数据丢失。
    生产环境需迁移到 PostgreSQL 持久化。
    """
    # PRODUCTION: 生产环境需迁移到 PostgreSQL 持久化存储

    def __init__(self) -> None:
        """初始化变更历史服务。"""
        self._entries: list[dict[str, Any]] = []

    async def record(
        self,
        document_id: str,
        user_id: str,
        action: str,
        detail: str = "",
        version: int = 1,
    ) -> ChangeLogEntry:
        """记录一条变更。

        Args:
            document_id: 文档 ID。
            user_id: 用户 ID。
            action: 操作类型。
            detail: 详情。
            version: 版本号。

        Returns:
            创建的变更记录。
        """
        entry_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": entry_id,
            "document_id": document_id,
            "user_id": user_id,
            "action": action,
            "detail": detail,
            "version": version,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._entries.append(entry)
        return ChangeLogEntry(**entry)

    async def get_history(
        self,
        document_id: str,
        limit: int = 50,
    ) -> list[ChangeLogEntry]:
        """获取文档的变更历史。

        Args:
            document_id: 文档 ID。
            limit: 返回条数上限。

        Returns:
            变更历史列表（时间倒序）。
        """
        results = [
            ChangeLogEntry(**e)
            for e in self._entries
            if e["document_id"] == document_id
        ]
        return sorted(
            results,
            key=lambda x: x.created_at or "",
            reverse=True,
        )[:limit]
