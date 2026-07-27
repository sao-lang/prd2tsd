"""工具基类 — 所有工具继承此类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.agents.context import ToolContext
from app.agents.result import ToolResult


class BaseTool(ABC):
    """工具基类 — 所有工具继承此类。

    每个工具定义：
    - name: LLM 通过此名称选择工具
    - description: 描述工具用途
    - parameters: Pydantic 参数模型 → 自动生成 JSON Schema
    """

    name: str = ""
    description: str = ""
    parameters: type[BaseModel] | None = None
    required_permissions: list[str] = []
    timeout: float = 30.0
    allowed_agents: list[str] = []  # 允许使用该工具的 Agent 列表（空 = 全部允许）

    @abstractmethod
    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        """执行工具逻辑。子类必须实现。

        Args:
            ctx: 工具执行上下文。
            **params: 由 LLM Function Calling 解析的参数。

        Returns:
            ToolResult 包含执行结果。
        """
        ...
