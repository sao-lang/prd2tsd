"""PII 检测护栏 — 前置/后置。"""

from __future__ import annotations

import re
from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class PIIDetectorGuardrail(Guardrail):
    """PII 检测护栏 — 前后置通用。"""

    name = "pii_detector"
    stage = "pre_llm"

    PII_PATTERNS = [
        (r"\b\d{17}[\dXx]\b", "身份证号"),
        (r"\b1[3-9]\d{9}\b", "手机号"),
        (r"\b\d{6}[- ]?\d{4}[- ]?\d{4}\b", "银行卡号"),
        (
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "邮箱地址",
        ),
    ]

    ACTION: str = "mask"  # mask / block / warn

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """执行 PII 脱敏护栏检查。"""
        masked = text
        found_pii = []

        for pattern, pii_type in self.PII_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                found_pii.append(f"{pii_type}({len(matches)}处)")
                masked = re.sub(pattern, "[PII_MASKED]", masked)

        if found_pii:
            reason = f"检测到 PII: {', '.join(found_pii)}"
            if self.ACTION == "block":
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    reason=reason,
                    severity="critical",
                )
            return GuardrailResult(
                passed=True,
                blocked=False,
                reason=reason,
                severity="warning",
                masked_text=masked,
            )

        return GuardrailResult(passed=True)
