"""C1 — Analysis Layer 工具函数。"""

from __future__ import annotations

import re
from typing import Any

from contracts.interfaces import DocumentSection


def parse_markdown_sections(text: str) -> list[DocumentSection]:
    """将 Markdown 文本按标题拆分为结构化章节。

    Args:
        text: 原始 Markdown 文本。

    Returns:
        章节列表（含层级关系）。
    """
    lines = text.splitlines()
    sections: list[DocumentSection] = []
    stack: list[tuple[int, DocumentSection]] = []  # (level, section)

    for line in lines:
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if header_match:
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            new_sec = DocumentSection(title=title, level=level, content="")

            # 找到父级
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].subsections.append(new_sec)

            stack.append((level, new_sec))
            sections.append(new_sec)
        elif sections:
            # 追加到当前章节
            sections[-1].content += line + "\n"

    return sections


async def call_llm_async(prompt: str, model: str | None = None, **kwargs: Any) -> str:
    """异步调用 LLM 获取文本结果。

    Args:
        prompt: 输入提示词。
        model: 指定模型名。
        **kwargs: 额外参数。

    Returns:
        LLM 返回的文本。LLM 不可用时返回空字符串。
    """
    from app.core.llm import llm_complete

    try:
        return await llm_complete(prompt, model=model, **kwargs)
    except Exception:
        return ""


def extract_json_from_llm(text: str) -> str:
    """从 LLM 返回文本中提取 JSON 部分。

    Args:
        text: LLM 返回文本（可能含 markdown 代码块）。

    Returns:
        纯 JSON 字符串。
    """
    # 尝试从 ```json ``` 代码块提取
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()

    # 尝试直接解析
    brace_start = text.find("{")
    if brace_start >= 0:
        return text[brace_start:].strip()

    bracket_start = text.find("[")
    if bracket_start >= 0:
        return text[bracket_start:].strip()

    return text.strip()
