"""EmptyResponseGuardrail — post_llm 阶段：检测 LLM 空响应。

当 LLM 返回空字符串时判定为失败，触发重试决策。
"""

from __future__ import annotations

from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class EmptyResponseGuardrail(Guardrail):
    """空响应护栏 — LLM 返回空字符串时触发重试。

    空响应通常表示 LLM 调用失败（网络超时/被限流/模型异常），
    不应作为有效结果传递给下游节点。
    """

    name = "empty_response_guardrail"
    stage = "post_llm"

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """检查 LLM 响应是否为空。

        Args:
            text: LLM 输出文本。
            context: 上下文信息。

        Returns:
            护栏检查结果。
        """
        if not text or not text.strip():
            return GuardrailResult(
                passed=False,
                reason="LLM 返回空响应",
                severity="warning",
            )

        return GuardrailResult(passed=True, reason="响应非空")
