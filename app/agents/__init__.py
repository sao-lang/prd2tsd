"""Agent 工具系统 — Tool Registry / BaseTool / ToolContext / ToolResult。

Block F §2 — 4 个 Agent 共享的工具注册器。
Phase 5: ToolRegistry 已废弃，待迁移至 LangChain @tool + ToolNode。
"""

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.registry import ToolRegistry  # noqa: F401 — 保留兼容，已废弃
from app.agents.result import ToolResult

__all__ = [
    "BaseTool",
    "ToolContext",
    "ToolResult",
]
