"""行内评论服务。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.collaboration.models import CommentCreate, CommentOut
from app.core.logger import get_logger

logger = get_logger("prd2tsd.comment")


class CommentService:
    """行内评论服务。

    支持在文档指定段落添加评论和回复。
    注意：当前使用内存存储（self._comments），重启后数据丢失。
    生产环境需迁移到 PostgreSQL 持久化。
    """
    # PRODUCTION: 生产环境需迁移到 PostgreSQL 持久化存储

    def __init__(self) -> None:
        """初始化评论服务。"""
        self._comments: dict[str, dict[str, Any]] = {}  # id → comment

    async def add_comment(
        self,
        document_id: str,
        user_id: str,
        data: CommentCreate,
    ) -> CommentOut:
        """添加评论。

        Args:
            document_id: 文档 ID。
            user_id: 用户 ID。
            data: 评论内容。

        Returns:
            创建的评论。
        """
        comment_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        entry: dict[str, Any] = {
            "id": comment_id,
            "document_id": document_id,
            "user_id": user_id,
            "content": data.content,
            "selection_text": data.selection_text,
            "selection_start": data.selection_start,
            "selection_end": data.selection_end,
            "parent_comment_id": data.parent_comment_id,
            "resolved": False,
            "created_at": now,
            "updated_at": now,
        }
        self._comments[comment_id] = entry
        logger.info("评论已添加: doc=%s, comment=%s", document_id, comment_id[:8])
        return CommentOut(**entry)

    async def resolve_comment(self, comment_id: str) -> bool:
        """标记评论为已解决。

        Args:
            comment_id: 评论 ID。

        Returns:
            是否成功。
        """
        comment = self._comments.get(comment_id)
        if not comment:
            return False
        comment["resolved"] = True
        comment["updated_at"] = datetime.now(UTC).isoformat()
        return True

    async def get_comments(
        self,
        document_id: str,
        include_resolved: bool = False,
    ) -> list[CommentOut]:
        """获取文档的评论列表。

        Args:
            document_id: 文档 ID。
            include_resolved: 是否包含已解决的评论。

        Returns:
            评论列表。
        """
        results = []
        for c in self._comments.values():
            if c["document_id"] != document_id:
                continue
            if not include_resolved and c["resolved"]:
                continue
            results.append(CommentOut(**c))
        return sorted(results, key=lambda x: x.created_at or "")

    async def delete_comment(self, comment_id: str) -> bool:
        """删除评论。

        Args:
            comment_id: 评论 ID。

        Returns:
            是否成功。
        """
        if comment_id in self._comments:
            del self._comments[comment_id]
            return True
        return False
