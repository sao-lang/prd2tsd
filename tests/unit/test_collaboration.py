"""协作文档单元测试。"""

from __future__ import annotations

import pytest

from app.collaboration.comment import CommentService
from app.collaboration.models import CommentCreate, SuggestionCreate
from app.collaboration.service import CollaborationService
from app.collaboration.suggestion import SuggestionService


class TestCommentService:
    """评论服务单元测试。"""

    @pytest.mark.asyncio
    async def test_add_and_get_comments(self) -> None:
        """验证添加并获取评论。"""
        svc = CommentService()
        data = CommentCreate(document_id="doc1", content="测试评论", selection_text="选中文本")
        created = await svc.add_comment("doc1", "user1", data)
        assert created.content == "测试评论"

        comments = await svc.get_comments("doc1")
        assert len(comments) == 1

    @pytest.mark.asyncio
    async def test_resolve_comment(self) -> None:
        """验证解决评论。"""
        svc = CommentService()
        data = CommentCreate(document_id="doc1", content="待解决")
        created = await svc.add_comment("doc1", "user1", data)
        assert created.resolved is False

        await svc.resolve_comment(created.id)
        comments = await svc.get_comments("doc1", include_resolved=True)
        resolved = [c for c in comments if c.id == created.id]
        assert resolved[0].resolved is True

    @pytest.mark.asyncio
    async def test_resolve_nonexistent(self) -> None:
        """验证解决不存在的评论返回 False。"""
        svc = CommentService()
        assert await svc.resolve_comment("nonexistent") is False

    @pytest.mark.asyncio
    async def test_delete_comment(self) -> None:
        """验证删除评论。"""
        svc = CommentService()
        data = CommentCreate(document_id="doc1", content="待删除")
        created = await svc.add_comment("doc1", "user1", data)
        assert await svc.delete_comment(created.id) is True
        assert await svc.delete_comment("nonexistent") is False


class TestSuggestionService:
    """建议服务单元测试。"""

    @pytest.mark.asyncio
    async def test_create_and_approve(self) -> None:
        """验证创建并通过建议。"""
        svc = SuggestionService()
        data = SuggestionCreate(
            document_id="doc1",
            original_text="旧文本",
            suggested_text="新文本",
            reason="更准确",
        )
        created = await svc.create("doc1", "user1", data)
        assert created.status == "pending"

        approved = await svc.approve(created.id)
        assert approved is not None
        assert approved.status == "approved"

    @pytest.mark.asyncio
    async def test_reject(self) -> None:
        """验证拒绝建议。"""
        svc = SuggestionService()
        data = SuggestionCreate(document_id="doc1", original_text="a", suggested_text="b")
        created = await svc.create("doc1", "user1", data)
        rejected = await svc.reject(created.id)
        assert rejected is not None
        assert rejected.status == "rejected"

    @pytest.mark.asyncio
    async def test_approve_nonexistent(self) -> None:
        """验证审批不存在的建议返回 None。"""
        svc = SuggestionService()
        assert await svc.approve("nonexistent") is None


class TestCollaborationService:
    """协作文档服务集成测试。"""

    @pytest.mark.asyncio
    async def test_add_comment_records_changelog(self) -> None:
        """验证添加评论自动记录变更历史。"""
        svc = CollaborationService()
        data = CommentCreate(document_id="doc1", content="集成测试")
        await svc.add_comment("doc1", "user1", data)

        history = await svc.get_history("doc1")
        assert len(history) >= 1
        assert history[0].action == "comment_added"

    @pytest.mark.asyncio
    async def test_create_suggestion_records_changelog(self) -> None:
        """验证创建建议自动记录变更历史。"""
        svc = CollaborationService()
        data = SuggestionCreate(document_id="doc1", original_text="a", suggested_text="b")
        await svc.create_suggestion("doc1", "user1", data)

        history = await svc.get_history("doc1")
        assert any(h.action == "suggestion_created" for h in history)
