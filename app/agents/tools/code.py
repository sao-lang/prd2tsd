"""代码工具 — GenerateCodeTool, ReadCodeTool。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.result import ToolResult


class GenerateCodeParams(BaseModel):
    """GenerateCodeTool 参数模型。"""

    specification: str = Field(description="代码规格说明")
    language: str = Field(default="python", description="编程语言")


class GenerateCodeTool(BaseTool):
    """代码生成工具 — 根据规格生成代码片段。"""

    name = "generate_code"
    description = "根据规格说明生成代码片段"
    parameters = GenerateCodeParams
    allowed_agents = ["generation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        specification = params.get("specification", "")
        language = params.get("language", "python")

        try:
            if ctx.llm:
                resp = await ctx.llm.complete(
                    prompt=f"请根据以下规格生成 {language} 代码：\n\n{specification}",
                    task_type="code_generation",
                )
            else:
                from app.llm_gateway import gateway
                resp = await gateway.complete(
                    prompt=f"请根据以下规格生成 {language} 代码：\n\n{specification}",
                    task_type="code_generation",
                )
            return ToolResult(
                success=True,
                data={"code": resp.content, "language": language},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ReadCodeParams(BaseModel):
    """ReadCodeTool 参数模型。"""

    code_path: str = Field(description="代码文件路径")
    max_lines: int = Field(default=100, description="最大行数")


class ReadCodeTool(BaseTool):
    """代码读取工具 — 读取工作空间中的代码文件。"""

    name = "read_code"
    description = "读取工作空间中的代码文件内容，用于分析和参考"
    parameters = ReadCodeParams
    allowed_agents = ["analysis", "planning", "generation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        code_path = params.get("code_path", "")
        max_lines = params.get("max_lines", 100)

        try:
            from app.document_management.repository import DocumentRepository

            repo = DocumentRepository()
            content = await repo.read_document(code_path, ctx.workspace_id)
            if content:
                lines = content.split("\n")[:max_lines]
                return ToolResult(
                    success=True,
                    data={
                        "code": "\n".join(lines),
                        "path": code_path,
                        "total_lines": len(content.split("\n")),
                    },
                )
            return ToolResult(success=False, error=f"代码文件未找到: {code_path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
