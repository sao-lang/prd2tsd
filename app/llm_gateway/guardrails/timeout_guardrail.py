"""TimeoutGuardrail — pre_llm 阶段：调用前检查 CircuitBreaker 状态。

当 CircuitBreaker 处于 OPEN 状态时，阻止 LLM 调用并触发降级路径。
"""

from __future__ import annotations

from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class TimeoutGuardrail(Guardrail):
    """超时/熔断护栏 — 调用前检查 CircuitBreaker 状态。

    当 CircuitBreaker 处于 OPEN 状态时，阻止 LLM 调用并返回 blocked=True，
    metadata 中写入降级建议供 LangGraph 条件边使用。
    """

    name = "timeout_guardrail"
    stage = "pre_llm"

    def __init__(self, circuit_breaker: Any = None) -> None:
        """初始化超时护栏。

        Args:
            circuit_breaker: CircuitBreaker 实例（可选，延迟注入）。
        """
        self._circuit_breaker = circuit_breaker

    def set_circuit_breaker(self, cb: Any) -> None:
        """注入 CircuitBreaker。

        Args:
            cb: CircuitBreaker 实例。
        """
        self._circuit_breaker = cb

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """检查 CircuitBreaker 状态。

        Args:
            text: 输入文本（未使用）。
            context: 上下文信息。

        Returns:
            护栏检查结果。
        """
        timeout_seconds = context.get("timeout_seconds")
        if isinstance(timeout_seconds, (int, float)) and timeout_seconds <= 0:
            return GuardrailResult(
                passed=False,
                blocked=True,
                reason="LLM 调用期限已耗尽",
                severity="critical",
            )

        configured_breakers = context.get("circuit_breakers")
        if isinstance(configured_breakers, list) and configured_breakers:
            if any(getattr(breaker, "is_available", False) for breaker in configured_breakers):
                return GuardrailResult(passed=True, reason="Failover 链至少有一个熔断器可用")
            return GuardrailResult(
                passed=False,
                blocked=True,
                reason="Failover 链全部处于熔断状态",
                severity="critical",
            )

        circuit_breaker = context.get("circuit_breaker") or self._circuit_breaker
        if circuit_breaker is None:
            return GuardrailResult(
                passed=False,
                blocked=True,
                reason="未找到目标 Provider 的熔断器",
                severity="critical",
            )

        state = getattr(circuit_breaker, "state", "closed")
        if not getattr(circuit_breaker, "is_available", state != "open"):
            return GuardrailResult(
                passed=False,
                blocked=True,
                reason="CircuitBreaker 已熔断，拒绝 LLM 调用",
                severity="critical",
            )

        if state == "half_open":
            return GuardrailResult(
                passed=True,
                reason="CircuitBreaker 半开，允许测试调用",
                severity="warning",
            )

        return GuardrailResult(passed=True, reason="CircuitBreaker 正常")
