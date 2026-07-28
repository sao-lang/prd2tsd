"""RetryDecisionGuardrail — post_llm 阶段：根据失败原因决定重试或降级。

综合 LLM 输出质量和调用状态，决定是否重试、使用降级模型、或直接失败。
结果写入 metadata 供 LangGraph 条件边使用。
"""

from __future__ import annotations

from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class RetryDecisionGuardrail(Guardrail):
    """重试决策护栏 — 根据失败原因决定重试或降级。

    决策逻辑：
    - 空响应 → retry=True（最多 3 次）
    - JSON 解析失败 → retry=True（带格式提示）
    - 超时 → retry=True + fallback_model
    - 内容被 ContentSafety 拦截 → blocked=True
    """

    name = "retry_decision_guardrail"
    stage = "post_llm"

    def __init__(
        self,
        max_retries: int = 3,
        fallback_model: str = "gpt-4o-mini",
    ) -> None:
        """初始化重试决策护栏。

        Args:
            max_retries: 最大重试次数。
            fallback_model: 降级模型名。
        """
        self.max_retries = max_retries
        self.fallback_model = fallback_model

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """根据失败原因决定重试策略。

        Args:
            text: LLM 输出文本。
            context: 上下文信息，包含:
                - retry_count: 当前重试次数
                - error_type: 错误类型（empty_response / json_parse_error / timeout / content_blocked）
                - previous_guardrail_results: 之前护栏的结果列表

        Returns:
            护栏检查结果，metadata 中包含 retry 决策信息。
        """
        retry_count = context.get("retry_count", 0)
        error_type = context.get("error_type", "")
        previous_results = context.get("previous_guardrail_results", [])

        # 检查之前的护栏是否已阻止
        for prev_result in previous_results:
            if hasattr(prev_result, "blocked") and prev_result.blocked:
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    reason=f"已被护栏阻止: {getattr(prev_result, 'reason', 'unknown')}",
                    severity="critical",
                )

        # 超过最大重试次数 → 不再重试
        if retry_count >= self.max_retries:
            return GuardrailResult(
                passed=False,
                reason=f"已达最大重试次数 ({self.max_retries})",
                severity="critical",
            )

        # 根据错误类型决策
        if error_type == "empty_response":
            return GuardrailResult(
                passed=False,
                reason="空响应，建议重试",
                severity="warning",
            )

        if error_type == "json_parse_error":
            return GuardrailResult(
                passed=False,
                reason="JSON 解析失败，建议带格式提示重试",
                severity="warning",
            )

        if error_type == "timeout":
            return GuardrailResult(
                passed=False,
                reason=f"超时，建议使用降级模型 {self.fallback_model}",
                severity="warning",
            )

        if error_type == "content_blocked":
            return GuardrailResult(
                passed=False,
                blocked=True,
                reason="内容被安全护栏拦截",
                severity="critical",
            )

        # 默认通过
        return GuardrailResult(passed=True, reason="无需重试")
