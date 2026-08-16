"""护栏管理器 — 统一注册和执行所有护栏。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult

logger = get_logger("prd2tsd.guardrails")


class GuardrailManager:
    """护栏管理器 — 统一注册和执行所有护栏。"""

    def __init__(self) -> None:
        self._pre_guards: list[Guardrail] = []  # LLM 调用前
        self._post_guards: list[Guardrail] = []  # LLM 调用后

    def register(self, guard: Guardrail) -> None:
        """注册护栏。

        Args:
            guard: Guardrail 实例。
        """
        if guard.stage == "pre_llm":
            self._pre_guards.append(guard)
        else:
            self._post_guards.append(guard)
        logger.info("护栏已注册: %s (stage=%s)", guard.name, guard.stage)

    async def check_input(
        self,
        text: str,
        context: dict[str, Any],
    ) -> list[GuardrailResult]:
        """执行所有前置护栏。返回所有检查结果。"""
        results: list[GuardrailResult] = []
        for guard in self._pre_guards:
            result = await guard.check(text, context)
            result.name = guard.name
            results.append(result)
            if result.blocked:
                logger.warning("输入被护栏拦截: %s — %s", guard.name, result.reason)
                break
        return results

    async def check_output(
        self,
        text: str,
        context: dict[str, Any],
    ) -> list[GuardrailResult]:
        """执行所有后置护栏。返回所有检查结果。"""
        results: list[GuardrailResult] = []
        for guard in self._post_guards:
            result = await guard.check(text, context)
            result.name = guard.name
            results.append(result)
            if result.blocked and result.severity == "critical":
                break
        return results
