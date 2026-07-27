"""ToolRegistry 单元测试。"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.registry import ToolNotFoundError, ToolRegistry, ToolTimeoutError
from app.agents.result import ToolResult


class TestParams(BaseModel):
    """测试参数模型。"""

    input_text: str = Field(description="输入文本")


class EchoTool(BaseTool):
    """回显工具 — 测试用。"""

    name = "echo"
    description = "回显输入"
    parameters = TestParams
    allowed_agents = ["test_agent"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        return ToolResult(success=True, data=params.get("input_text", ""))


class SlowTool(BaseTool):
    """慢工具 — 测试超时。"""

    name = "slow"
    description = "慢操作"
    parameters = TestParams
    timeout = 0.1

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        import asyncio
        await asyncio.sleep(10)
        return ToolResult(success=True, data="done")


class TestToolRegistry:
    """ToolRegistry 测试。"""

    def setup_method(self):
        ToolRegistry._tools.clear()
        ToolRegistry.register(EchoTool())

    def test_register_and_get_schemas(self):
        """测试注册和获取 Schema。"""
        schemas = ToolRegistry.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "echo"

    def test_get_schemas_by_agent(self):
        """测试按 Agent 筛选。"""
        schemas = ToolRegistry.get_schemas(agent_name="test_agent")
        assert len(schemas) == 1

        schemas = ToolRegistry.get_schemas(agent_name="other_agent")
        assert len(schemas) == 0

    def test_get_tool_names(self):
        """测试获取工具名列表。"""
        names = ToolRegistry.get_tool_names()
        assert "echo" in names

    def test_unregister(self):
        """测试注销工具。"""
        ToolRegistry.unregister("echo")
        assert "echo" not in ToolRegistry.get_tool_names()

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """测试工具执行成功。"""
        ctx = ToolContext(task_id="test", workspace_id="test")
        result = await ToolRegistry.execute("echo", ctx, input_text="hello")
        assert result.success is True
        assert result.data == "hello"

    @pytest.mark.asyncio
    async def test_execute_not_found(self):
        """测试工具未找到。"""
        ctx = ToolContext()
        with pytest.raises(ToolNotFoundError):
            await ToolRegistry.execute("nonexistent", ctx)

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """测试工具超时。"""
        ToolRegistry.register(SlowTool())
        ctx = ToolContext()
        with pytest.raises(ToolTimeoutError):
            await ToolRegistry.execute("slow", ctx, input_text="test")

    def test_schema_has_parameters(self):
        """测试 Schema 包含参数。"""
        schemas = ToolRegistry.get_schemas()
        assert "parameters" in schemas[0]["function"]
        params = schemas[0]["function"]["parameters"]
        assert "input_text" in params["properties"]
