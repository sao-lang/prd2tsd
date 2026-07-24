"""C4 — Evaluation Layer 工具函数。"""

from __future__ import annotations

import json
import re
from typing import Any


async def call_llm(prompt: str, model: str | None = None, **kwargs: Any) -> str:
    """异步调用 LLM，失败时返回空字符串。

    Args:
        prompt: 输入提示词。
        model: 模型名。
        **kwargs: 额外参数。

    Returns:
        LLM 返回文本。不可用时返回空字符串。
    """
    from app.core.llm import llm_complete

    try:
        return await llm_complete(prompt, model=model, **kwargs)
    except Exception:
        return ""


def parse_score(response: str, field: str = "score") -> float:
    """从 LLM 返回的 JSON 中提取评分。

    Args:
        response: LLM 返回文本。
        field: 要提取的字段名。

    Returns:
        提取的分数（0-10），失败时返回 5.0 默认值。
    """
    if not response:
        return 5.0
    try:
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            data: dict[str, Any] = json.loads(json_match.group())
            val = data.get(field, 5.0)
            return float(val)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return 5.0
