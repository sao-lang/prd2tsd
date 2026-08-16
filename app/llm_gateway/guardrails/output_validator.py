"""输出格式校验护栏 — 后置。"""

from __future__ import annotations

import json
from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class OutputValidatorGuardrail(Guardrail):
    """输出格式校验护栏 — 后置。

    校验 LLM 输出是否为合法的 JSON（当期望 JSON 输出时）。
    """

    name = "output_validator"
    stage = "post_llm"

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """执行输出格式校验护栏检查。"""
        # 仅当任务期望 JSON 输出时校验
        task_type = context.get("task_type", "")
        expected_json = context.get("expected_json", False)

        if not expected_json and "json" not in task_type:
            return GuardrailResult(passed=True)

        # 检查是否包含可解析的 JSON
        text_stripped = text.strip()
        if text_stripped.startswith("```"):
            # 从代码块提取
            import re

            m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
            if m:
                text_stripped = m.group(1).strip()

        try:
            json.loads(text_stripped)
            return GuardrailResult(passed=True)
        except (json.JSONDecodeError, ValueError):
            return GuardrailResult(
                passed=False,
                blocked=False,
                reason="输出不是合法的 JSON 格式（期望 JSON 输出）",
                severity="warning",
            )
