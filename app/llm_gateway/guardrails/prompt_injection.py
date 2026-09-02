"""Prompt 注入检测护栏 — 前置。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.llm_gateway.guardrails.base import Guardrail, GuardrailResult


class PromptInjectionGuardrail(Guardrail):
    """Prompt 注入检测护栏 — 前置。"""

    name = "prompt_injection"
    stage = "pre_llm"

    _ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
    _WHITESPACE = re.compile(r"\s+")
    RISK_PATTERNS: tuple[tuple[str, int, str], ...] = (
        (
            r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|system|developer)\b",
            4,
            "instruction_override",
        ),
        (
            r"\b(reveal|show|print|repeat|leak|extract)\b.{0,40}\b(system|developer)"
            r"\s*(prompt|message|instructions?)\b",
            4,
            "prompt_exfiltration",
        ),
        (
            r"\b(act as|roleplay as|you are now)\b.{0,40}\b(dan|unrestricted|unlocked|developer|system)\b",
            3,
            "role_override",
        ),
        (r"<(system|developer|assistant)>|\[(system|developer)\]|^(system|developer)\s*:", 3, "role_delimiter"),
        (r"\b(base64|rot13|hex|unicode)\b.{0,50}\b(decode|instructions?|prompt)\b", 2, "encoded_instruction"),
        (r"忽略.{0,12}(之前|先前|以上|系统).{0,8}(指令|提示|要求)", 4, "zh_instruction_override"),
        (r"(泄露|显示|输出|复述).{0,12}(系统|开发者).{0,6}(提示词|指令|消息)", 4, "zh_prompt_exfiltration"),
        (r"(你现在是|扮演).{0,16}(无限制|开发者|系统|dan)", 3, "zh_role_override"),
    )

    def __init__(self, block_threshold: int = 5) -> None:
        """初始化风险评分阈值。"""
        self._block_threshold = max(1, block_threshold)

    @classmethod
    def _normalize(cls, text: str) -> str:
        """归一化兼容字符、零宽字符和空白，降低简单混淆绕过概率。"""
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = cls._ZERO_WIDTH.sub("", normalized)
        return cls._WHITESPACE.sub(" ", normalized).strip()

    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """执行 Prompt 注入检测护栏检查。"""
        normalized = self._normalize(text)
        matched: list[str] = []
        score = 0
        for pattern, weight, category in self.RISK_PATTERNS:
            if re.search(pattern, normalized, flags=re.IGNORECASE | re.DOTALL):
                matched.append(category)
                score += weight

        # 单一高置信度攻击信号应直接阻断；多个弱信号则按总分判定。
        high_confidence = any(weight >= 4 and category in matched for _, weight, category in self.RISK_PATTERNS)
        blocked = high_confidence or score >= self._block_threshold
        if blocked:
            return GuardrailResult(
                passed=False,
                blocked=True,
                reason=f"检测到 Prompt 注入风险: {','.join(matched)} (score={score})",
                severity="critical",
            )
        if score:
            return GuardrailResult(
                passed=True,
                reason=f"检测到低风险 Prompt 特征: {','.join(matched)} (score={score})",
                severity="warning",
            )
        return GuardrailResult(passed=True)
