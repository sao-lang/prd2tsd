"""协作文档服务 — 统一对外接口。"""

from __future__ import annotations

from app.collaboration.changelog import ChangeLogService
from app.collaboration.comment import CommentService
from app.collaboration.models import (
    ChangeLogEntry,
    CommentCreate,
    CommentOut,
    SuggestionCreate,
    SuggestionOut,
)
from app.collaboration.suggestion import SuggestionService
from app.core.logger import get_logger

logger = get_logger("prd2tsd.collaboration")


class CollaborationService:
    """协作文档服务 — 组合 评论/建议/变更历史。"""

    def __init__(
        self,
        comment_service: CommentService | None = None,
        suggestion_service: SuggestionService | None = None,
        changelog_service: ChangeLogService | None = None,
    ) -> None:
        """初始化协作文档服务。

        Args:
            comment_service: 评论服务。
            suggestion_service: 建议服务。
            changelog_service: 变更历史服务。
        """
        self.comments = comment_service or CommentService()
        self.suggestions = suggestion_service or SuggestionService()
        self.changelog = changelog_service or ChangeLogService()

    # ── 评论 ──

    async def add_comment(
        self,
        document_id: str,
        user_id: str,
        data: CommentCreate,
    ) -> CommentOut:
        """添加评论。"""
        result = await self.comments.add_comment(document_id, user_id, data)
        await self.changelog.record(document_id, user_id, "comment_added", data.content[:100])
        return result

    async def resolve_comment(self, comment_id: str) -> bool:
        """解决评论。"""
        return await self.comments.resolve_comment(comment_id)

    async def get_comments(
        self,
        document_id: str,
        resolved: bool = False,
    ) -> list[CommentOut]:
        """获取评论。"""
        return await self.comments.get_comments(document_id, resolved)

    # ── 建议 ──

    async def create_suggestion(
        self,
        document_id: str,
        user_id: str,
        data: SuggestionCreate,
    ) -> SuggestionOut:
        """创建建议。"""
        result = await self.suggestions.create(document_id, user_id, data)
        await self.changelog.record(
            document_id, user_id, "suggestion_created",
            f"建议修改: {data.original_text[:50]} → {data.suggested_text[:50]}",
        )
        return result

    async def approve_suggestion(self, suggestion_id: str) -> SuggestionOut | None:
        """审批通过。"""
        return await self.suggestions.approve(suggestion_id)

    async def reject_suggestion(self, suggestion_id: str) -> SuggestionOut | None:
        """拒绝。"""
        return await self.suggestions.reject(suggestion_id)

    async def get_suggestions(
        self,
        document_id: str,
        status: str | None = None,
    ) -> list[SuggestionOut]:
        """获取建议。"""
        return await self.suggestions.get_by_document(document_id, status)

    # ── 变更历史 ──

    async def get_history(
        self,
        document_id: str,
        limit: int = 50,
    ) -> list[ChangeLogEntry]:
        """获取变更历史。"""
        return await self.changelog.get_history(document_id, limit)


# 全局单例
collaboration_service = CollaborationService()
