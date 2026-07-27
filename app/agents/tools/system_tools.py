"""系统工具 — ReadTimeTool, ListFilesTool。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.result import ToolResult


class ReadTimeParams(BaseModel):
    """ReadTimeTool 参数模型。"""

    format: str = Field(default="iso", description="时间格式: iso / unix / readable")


class ReadTimeTool(BaseTool):
    """时间读取工具 — 获取当前系统时间。"""

    name = "read_time"
    description = "获取当前系统时间和日期"
    parameters = ReadTimeParams
    allowed_agents = ["analysis", "planning", "generation", "evaluation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        fmt = params.get("format", "iso")
        now = datetime.now(UTC)

        if fmt == "unix":
            data = now.timestamp()
        elif fmt == "readable":
            data = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            data = now.isoformat()

        return ToolResult(success=True, data=data)


class ListFilesParams(BaseModel):
    """ListFilesTool 参数模型。"""

    directory: str = Field(default="", description="目录路径")
    pattern: str = Field(default="*", description="文件匹配模式")


class ListFilesTool(BaseTool):
    """文件列表工具 — 列出工作空间中的文件。"""

    name = "list_files"
    description = "列出工作空间中指定目录的文件"
    parameters = ListFilesParams
    allowed_agents = ["analysis", "planning", "generation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        directory = params.get("directory", "")
        pattern = params.get("pattern", "*")

        try:
            from app.document_management.repository import DocumentRepository

            repo = DocumentRepository()
            files = await repo.list_files(
                directory=directory,
                pattern=pattern,
                workspace_id=ctx.workspace_id,
            )
            return ToolResult(
                success=True,
                data={
                    "files": [{"name": f.get("name", ""), "path": f.get("path", "")} for f in files],
                    "total": len(files),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
