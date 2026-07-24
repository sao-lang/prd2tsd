"""建议修改服务。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.collaboration.models import SuggestionCreate, SuggestionOut
from app.core.logger import get_logger

logger = get_logger("prd2tsd.suggestion")


class SuggestionService:
    """建议修改服务。

    支持：建议 → 审批（approve/reject）→ 应用。
    注意：当前使用内存存储（self._suggestions），重启后数据丢失。
    生产环境需迁移到 PostgreSQL 持久化。
    """
    # PRODUCTION: 生产环境需迁移到 PostgreSQL 持久化存储

    def __init__(self) -> None:
        """初始化建议服务。"""
        self._suggestions: dict[str, dict[str, Any]] = {}

    async def create(
        self,
        document_id: str,
        user_id: str,
        data: SuggestionCreate,
    ) -> SuggestionOut:
        """创建建议修改。

        Args:
            document_id: 文档 ID。
            user_id: 用户 ID。
            data: 建议内容。

        Returns:
            创建的建议。
        """
        sug_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        entry: dict[str, Any] = {
            "id": sug_id,
            "document_id": document_id,
            "user_id": user_id,
            "original_text": data.original_text,
            "suggested_text": data.suggested_text,
            "reason": data.reason,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        self._suggestions[sug_id] = entry
        logger.info("建议已创建: doc=%s, suggestion=%s", document_id, sug_id[:8])
        return SuggestionOut(**entry)

    async def approve(self, suggestion_id: str) -> SuggestionOut | None:
        """审批通过建议。

        Args:
            suggestion_id: 建议 ID。

        Returns:
            更新后的建议。
        """
        sug = self._suggestions.get(suggestion_id)
        if not sug:
            return None
        sug["status"] = "approved"
        sug["updated_at"] = datetime.now(UTC).isoformat()
        return SuggestionOut(**sug)

    async def reject(self, suggestion_id: str) -> SuggestionOut | None:
        """拒绝建议。

        Args:
            suggestion_id: 建议 ID。

        Returns:
            更新后的建议。
        """
        sug = self._suggestions.get(suggestion_id)
        if not sug:
            return None
        sug["status"] = "rejected"
        sug["updated_at"] = datetime.now(UTC).isoformat()
        return SuggestionOut(**sug)

    async def get_by_document(
        self,
        document_id: str,
        status: str | None = None,
    ) -> list[SuggestionOut]:
        """获取文档的建议列表。

        Args:
            document_id: 文档 ID。
            status: 按状态筛选。

        Returns:
            建议列表。
        """
        results = []
        for s in self._suggestions.values():
            if s["document_id"] != document_id:
                continue
            if status and s["status"] != status:
                continue
            results.append(SuggestionOut(**s))
        return sorted(results, key=lambda x: x.created_at or "")
