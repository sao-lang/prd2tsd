"""C3 — Generation Layer 工具函数。"""

from __future__ import annotations

from typing import Any


async def call_llm_async(prompt: str, model: str | None = None, **kwargs: Any) -> str:
    """异步调用 LLM。

    Args:
        prompt: 输入提示词。
        model: 模型名。
        **kwargs: 额外参数。

    Returns:
        LLM 返回文本。LLM 不可用时返回空字符串。
    """
    from app.core.logger import get_logger
    from app.llm_gateway import gateway

    try:
        node = kwargs.pop("node", "")
        resp = await gateway.complete(
            prompt=prompt,
            task_type="generation",
            layer="generation",
            node=node,
            model=model,
        )
        return resp.content
    except Exception as exc:
        get_logger("prd2tsd.generation").warning("LLM 调用失败（generation）: %s", exc)
        return ""
