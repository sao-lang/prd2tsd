"""文档列表路由回归测试。

回归：GET /api/v1/documents?q=... 搜索分支返回 SearchResultItem，
而 DocumentListResponse.items 声明为 DocumentResponse 导致序列化 500。
"""

from __future__ import annotations

import pytest

from app.api.routes.documents import DocumentListResponse, list_documents
from app.auth.middleware import _SCOPE_WS_ID
from app.document_management.models import SearchResult


class _FakeDocService:
    """文档服务桩：搜索返回 1 条结果，列表返回空。"""

    async def search_documents(
        self, db, workspace_id: str, query: str, page: int, page_size: int,
    ) -> list[SearchResult]:
        return [
            SearchResult(
                document_id="doc-1",
                title="架构文档",
                description="PRD 转 TSD",
                file_type="pdf",
                file_size=2048,
                score=0.92,
            ),
        ]

    async def list_documents(
        self, db, workspace_id: str, page: int, page_size: int,
        file_type: str | None, status: str | None, sort_by: str,
    ) -> tuple[list, int]:
        return [], 0


class _FakeRequest:
    """带工作空间上下文的 Request 桩。"""

    def __init__(self) -> None:
        self.scope = {_SCOPE_WS_ID: "ws-1"}


@pytest.mark.asyncio
async def test_list_documents_search_branch() -> None:
    """搜索分支构造 DocumentListResponse 不应抛 ValidationError。"""
    result = await list_documents(
        request=_FakeRequest(),  # type: ignore[arg-type]
        user_id="user-1",
        db=None,  # type: ignore[arg-type]
        svc=_FakeDocService(),  # type: ignore[arg-type]
        page=1,
        page_size=20,
        file_type=None,
        status=None,
        sort_by="created_at",
        q="架构",
    )

    assert isinstance(result, DocumentListResponse)
    assert result.total == 1
    assert result.items[0].document_id == "doc-1"
    assert result.items[0].score == 0.92


@pytest.mark.asyncio
async def test_list_documents_list_branch() -> None:
    """无 q 时列表分支仍返回 DocumentResponse 列表。"""
    result = await list_documents(
        request=_FakeRequest(),  # type: ignore[arg-type]
        user_id="user-1",
        db=None,  # type: ignore[arg-type]
        svc=_FakeDocService(),  # type: ignore[arg-type]
        page=1,
        page_size=20,
        file_type=None,
        status=None,
        sort_by="created_at",
        q=None,
    )

    assert isinstance(result, DocumentListResponse)
    assert result.items == []
