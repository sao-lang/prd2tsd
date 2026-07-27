"""全局工具注册器 — 所有 Agent 共享。

职责：
- 注册/注销工具
- 生成 JSON Schema（给 LLM Function Calling）
- 按权限/角色筛选工具
- 执行工具（含超时/鉴权/追踪）
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.result import ToolResult
from app.core.logger import get_logger

logger = get_logger("prd2tsd.tool_registry")


class ToolNotFoundError(Exception):
    """工具未注册异常。"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"工具未注册: {name}")


class ToolPermissionError(Exception):
    """工具权限不足异常。"""

    def __init__(self, name: str, missing_perms: list[str]) -> None:
        self.name = name
        self.missing_perms = missing_perms
        super().__init__(f"无权限调用工具 {name}: 缺少 {missing_perms}")


class ToolTimeoutError(Exception):
    """工具执行超时异常。"""

    def __init__(self, name: str, timeout: float) -> None:
        self.name = name
        self.timeout = timeout
        super().__init__(f"工具 {name} 执行超时 ({timeout}s)")


class ToolRegistry:
    """全局工具注册器 — 所有 Agent 共享。"""

    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """注册工具。重复注册会覆盖。

        Args:
            tool: BaseTool 实例。
        """
        cls._tools[tool.name] = tool
        logger.info("工具已注册: %s (%s)", tool.name, tool.description[:50])

    @classmethod
    def unregister(cls, name: str) -> None:
        """注销工具。

        Args:
            name: 工具名称。
        """
        cls._tools.pop(name, None)
        logger.info("工具已注销: %s", name)

    @classmethod
    def get_schemas(
        cls,
        agent_name: str = "",
        permissions: list[str] | None = None,
    ) -> list[dict]:
        """返回工具的 OpenAI Function Calling Schema。

        Args:
            agent_name: 按 Agent 筛选（为空返回全部）。
            permissions: 按权限筛选（为空不限制）。

        Returns:
            OpenAI tools 参数格式的列表。
        """
        tools = list(cls._tools.values())
        if agent_name:
            tools = [
                t for t in tools
                if not t.allowed_agents or agent_name in t.allowed_agents
            ]
        if permissions:
            tools = [
                t for t in tools
                if not t.required_permissions
                or all(p in permissions for p in t.required_permissions)
            ]
        return [
            cls._tool_to_schema(t)
            for t in tools
        ]

    @classmethod
    def get_tool_names(cls) -> list[str]:
        """获取所有已注册的工具名称。"""
        return list(cls._tools.keys())

    @classmethod
    async def execute(
        cls,
        name: str,
        ctx: ToolContext,
        **params: Any,
    ) -> ToolResult:
        """执行工具（含超时/追踪/鉴权）。

        Args:
            name: 工具名。
            ctx: 执行上下文。
            **params: 执行参数。

        Returns:
            ToolResult。

        Raises:
            ToolNotFoundError: 工具未注册。
            ToolPermissionError: 无权限调用。
            ToolTimeoutError: 执行超时。
        """
        tool = cls._tools.get(name)
        if not tool:
            raise ToolNotFoundError(name)

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                tool.execute(ctx, **params),
                timeout=tool.timeout,
            )
            result.duration_ms = (time.monotonic() - start) * 1000
            return result
        except TimeoutError:
            raise ToolTimeoutError(name, tool.timeout) from None

    @classmethod
    def _tool_to_schema(cls, tool: BaseTool) -> dict:
        """将工具转换为 OpenAI Function Calling Schema。"""
        schema: dict = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
            },
        }
        if tool.parameters:
            schema["function"]["parameters"] = tool.parameters.model_json_schema()
        return schema
