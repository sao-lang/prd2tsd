"""Prompt 构建器 — 统一管理 System Prompt + User Prompt + 格式约束。"""

from __future__ import annotations

from typing import Any

from app.llm_gateway.output_parser import PydanticOutputParser


class PromptBuilder:
    """Prompt 构建器 — 统一管理 System Prompt + User Prompt + 格式约束。"""

    def __init__(self, system_prompt: str = ""):
        """初始化 Prompt 构建器。

        Args:
            system_prompt: 系统提示词（可选）。
        """
        self.system_prompt = system_prompt

    def build(
        self,
        user_prompt: str,
        output_parser: PydanticOutputParser | None = None,
        use_response_format: bool = False,
    ) -> dict:
        """构建完整的 Prompt（含 system message）。

        Args:
            user_prompt: 用户输入。
            output_parser: 输出解析器（可选）。
            use_response_format: 是否使用 API 原生 JSON 模式。

        Returns:
            {"messages": [...], "response_format": ... | None}
        """
        messages: list[dict[str, str]] = []

        # System prompt
        system_content = self.system_prompt
        if output_parser and not use_response_format:
            format_instruction = output_parser.get_format_instruction()
            system_content = (
                system_content + "\n\n" + format_instruction if system_content else format_instruction
            )

        if system_content:
            messages.append({"role": "system", "content": system_content})

        # User prompt
        messages.append({"role": "user", "content": user_prompt})

        result: dict[str, Any] = {"messages": messages}

        # response_format（原生方案）
        if output_parser and use_response_format:
            result["response_format"] = output_parser.get_response_format()

        return result
