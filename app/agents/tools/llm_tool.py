"""LLM 工具 — CallLLMTool。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import BaseTool
from app.agents.context import ToolContext
from app.agents.result import ToolResult


class CallLLMParams(BaseModel):
    """CallLLMTool 参数模型。"""

    prompt: str = Field(description="发送给 LLM 的提示词")
    task_type: str = Field(default="default", description="任务类型")
    temperature: float | None = Field(default=None, description="温度参数")
    max_tokens: int | None = Field(default=None, description="最大输出 Token 数")


class CallLLMTool(BaseTool):
    """LLM 调用工具 — 让 Agent 能够调用 LLM 处理子任务。"""

    name = "call_llm"
    description = "调用 LLM 处理文本生成、分析、总结等子任务"
    parameters = CallLLMParams
    allowed_agents = ["analysis", "planning", "generation", "evaluation"]

    async def execute(self, ctx: ToolContext, **params: Any) -> ToolResult:
        prompt = params.get("prompt", "")
        task_type = params.get("task_type", "default")
        temperature = params.get("temperature")
        max_tokens = params.get("max_tokens")

        try:
            kwargs: dict[str, Any] = {"prompt": prompt, "task_type": task_type}
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens

            # 尝试使用上下文的 LLM
            if ctx.llm:
                resp = await ctx.llm.complete(**kwargs)
            else:
                from app.llm_gateway import gateway
                resp = await gateway.complete(**kwargs)

            return ToolResult(
                success=True,
                data=resp.content,
                tokens_consumed=(resp.input_tokens or 0) + (resp.output_tokens or 0),
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
