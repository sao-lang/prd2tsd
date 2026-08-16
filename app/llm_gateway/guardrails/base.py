"""护栏基类 — 可插拔的输入/输出拦截器。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class GuardrailResult:
    """护栏检查结果。"""

    passed: bool
    name: str = ""  # 触发该结果的护栏名（由 GuardrailManager 填充）
    blocked: bool = False
    reason: str = ""
    severity: str = "info"  # info / warning / critical
    masked_text: str | None = None  # 脱敏后的文本


class Guardrail(ABC):
    """护栏基类 — 可插拔。"""

    name: str = ""
    stage: Literal["pre_llm", "post_llm"] = "pre_llm"

    @abstractmethod
    async def check(self, text: str, context: dict[str, Any]) -> GuardrailResult:
        """执行护栏检查。

        Args:
            text: 输入或输出文本。
            context: 上下文（含 task_type/user_id/workspace_id 等）。

        Returns:
            检查结果。
        """
        ...
