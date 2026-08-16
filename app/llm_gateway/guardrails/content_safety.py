"""内容安全检测护栏 — 后置。"""

from __future__ import annotations

import re
from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class ContentSafetyGuardrail(Guardrail):
    """内容安全检测护栏 — 后置。"""

    name = "content_safety"
    stage = "post_llm"

    BLOCKED_CONTENT = [
        r"(?i)(api_key|sk-[a-z0-9]{32,})",
        r"(?i)(secret|private_key)[\s:=]+['\"]?\w{16,}",
        r"(?i)(password|passwd)[\s:=]+['\"]?\w{8,}",
        r"(?i)(token|access_key)[\s:=]+['\"]?\w{16,}",
        r"(?i)-----BEGIN (RSA |EC )?PRIVATE KEY-----",
    ]

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """执行内容安全护栏检查。"""
        for pattern in self.BLOCKED_CONTENT:
            if re.search(pattern, text):
                return GuardrailResult(
                    passed=False,
                    blocked=True,
                    reason=f"输出包含敏感信息: {pattern}",
                    severity="critical",
                    masked_text=re.sub(pattern, "[MASKED]", text),
                )
        return GuardrailResult(passed=True)
