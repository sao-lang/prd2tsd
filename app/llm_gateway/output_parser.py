"""Pydantic 输出解析器 — 两步策略：API 原生 response_format → Prompt 约束 + 后处理。

策略：
1. 优先使用 OpenAI response_format（原生 JSON 约束，最可靠）
2. 降级使用 Prompt 约束 + 后处理解析
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError


class OutputParseError(Exception):
    """LLM 输出解析失败异常。"""

    def __init__(self, model_name: str, text: str, detail: str = "") -> None:
        self.model_name = model_name
        self.text = text[:200]
        self.detail = detail
        msg = f"无法将 LLM 输出解析为 {model_name}: {self.text}"
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


class PydanticOutputParser:
    """Pydantic 输出解析器 — 两步策略。

    策略：
    1. 优先使用 OpenAI response_format（原生 JSON 约束，最可靠）
    2. 降级使用 Prompt 约束 + 后处理解析
    """

    def __init__(self, pydantic_model: type[BaseModel]):
        """初始化解析器。

        Args:
            pydantic_model: Pydantic 模型类。
        """
        self.pydantic_model = pydantic_model
        self.schema = pydantic_model.model_json_schema()

    def get_response_format(self) -> dict[str, Any]:
        """获取 OpenAI response_format 参数。"""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": self.pydantic_model.__name__,
                "strict": True,
                "schema": self.schema,
            },
        }

    def get_format_instruction(self) -> str:
        """获取 Prompt 格式指令（response_format 不可用时降级使用）。"""
        schema_str = json.dumps(self.schema, indent=2, ensure_ascii=False)
        return f"""
请严格按照以下 JSON Schema 输出，不要包含其他说明文字：
```json
{schema_str}
```
"""

    def parse(self, text: str) -> BaseModel:
        """解析 LLM 输出为 Pydantic 模型。

        步骤：
        1. 尝试直接 json.loads
        2. 尝试从 ```json 代码块提取
        3. 尝试从 { } 提取
        4. 全部失败 → 抛 ParseError

        Args:
            text: LLM 输出的原始文本。

        Returns:
            解析后的 Pydantic 模型。

        Raises:
            OutputParseError: 解析失败时抛出。
        """
        model_name = self.pydantic_model.__name__

        # 1. 尝试直接解析
        try:
            data = json.loads(text)
            return self.pydantic_model(**data)
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e

        # 2. 从 ```json 代码块提取
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return self.pydantic_model(**data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = e

        # 3. 从第一个 { 提取（只提取到匹配的 }）
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            brace_end = -1
            for i, c in enumerate(text[brace_start:]):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        brace_end = brace_start + i + 1
                        break
            if brace_end > brace_start:
                try:
                    data = json.loads(text[brace_start:brace_end])
                    return self.pydantic_model(**data)
                except (json.JSONDecodeError, ValidationError) as e:
                    last_error = e

        raise OutputParseError(
            model_name=model_name,
            text=text,
            detail=str(last_error) if last_error else "",
        )
