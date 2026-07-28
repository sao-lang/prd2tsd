"""C3 — Generation Layer 工具函数。"""

from __future__ import annotations

from typing import Any


async def call_llm_async(prompt: str, model: str | None = None, **kwargs: Any) -> str:
    """异步调用 LLM — 使用 GatewayChatModel（LangChain 适配器）。

    Args:
        prompt: 输入提示词。
        model: 模型名。
        **kwargs: 额外参数（node 等）。

    Returns:
        LLM 返回文本。不可用时返回空字符串。
    """
    from app.core.logger import get_logger
    from app.llm_gateway.langchain_adapter import GatewayChatModel

    try:
        node = kwargs.pop("node", "")
        llm = GatewayChatModel(
            task_type="generation",
            layer="generation",
            node=node,
            default_model=model or "deepseek-chat",
        )
        resp = await llm.ainvoke(prompt)
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception as exc:
        get_logger("prd2tsd.generation").warning("LLM 调用失败（generation）: %s", exc)
        return ""
