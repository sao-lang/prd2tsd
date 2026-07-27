"""Prompt 注入检测护栏 — 前置。"""

from __future__ import annotations

import re
from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class PromptInjectionGuardrail(Guardrail):
    """Prompt 注入检测护栏 — 前置。"""

    name = "prompt_injection"
    stage = "pre_llm"

    INJECTION_PATTERNS = [
        r"(?i)ignore all previous instructions",
        r"(?i)disregard your system prompt",
        r"(?i)you are now (free|released|unlocked)",
        r"(?i)you must act as",
        r"(?i)you are not (an AI|a language model)",
        r"(?i)system prompt:",
        r"(?i)forget everything",
        r"(?i)你被解放了",
        r"(?i)忽略之前的指令",
        r"(?i)忽略所有指示",
        r"(?i)忘记之前的",
    ]

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, text):
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    reason=f"检测到 Prompt 注入模式: {pattern}",
                    severity="critical",
                )
        return GuardrailResult(passed=True)
