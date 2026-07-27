"""文档工具 — ReadFileTool, SearchDocTool。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.result import ToolResult


class ReadFileParams(BaseModel):
    """ReadFileTool 参数模型。"""

    file_path: str = Field(description="文件路径")
    max_length: int = Field(default=2000, description="最大读取字符数")


class ReadFileTool(BaseTool):
    """文件读取工具 — 读取工作空间中的文档文件。"""

    name = "read_file"
    description = "读取工作空间中指定路径的文档文件内容"
    parameters = ReadFileParams
    allowed_agents = ["analysis", "planning", "generation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        file_path = params.get("file_path", "")
        max_length = params.get("max_length", 2000)

        try:
            from app.document_management.repository import DocumentRepository

            repo = DocumentRepository()
            content = await repo.read_document(file_path, ctx.workspace_id)
            if content:
                return ToolResult(
                    success=True,
                    data={"content": content[:max_length], "path": file_path},
                )
            return ToolResult(success=False, error=f"文件未找到: {file_path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SearchDocParams(BaseModel):
    """SearchDocTool 参数模型。"""

    query: str = Field(description="搜索查询")
    workspace_id: str = Field(default="", description="工作空间 ID")


class SearchDocTool(BaseTool):
    """文档搜索工具 — 搜索工作空间中的管理文档。"""

    name = "search_doc"
    description = "搜索工作空间中的文档，支持全文检索"
    parameters = SearchDocParams
    allowed_agents = ["analysis", "planning", "generation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        query = params.get("query", "")
        workspace_id = params.get("workspace_id", ctx.workspace_id)

        try:
            from app.document_management.search import DocumentSearchService

            service = DocumentSearchService()
            results = await service.search(
                query=query,
                workspace_id=workspace_id or ctx.workspace_id,
                top_k=5,
            )
            return ToolResult(
                success=True,
                data={
                    "results": [
                        {"title": doc.get("title", ""), "snippet": doc.get("content", "")[:200]}
                        for doc in results
                    ],
                    "total": len(results),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
