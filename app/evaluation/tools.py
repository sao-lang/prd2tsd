"""C4 — Evaluation Layer 工具函数。

Phase 6 清理：parse_score 已删除，节点直接使用 PydanticOutputParser(ScoreResult)。
call_llm 保留用于 scoring.py 的批量评分调用。
"""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from app.core.logger import get_logger

logger = get_logger("prd2tsd.evaluation")


class ScoreResult(BaseModel):
    """评分结果 — LLM 结构化输出。"""

    score: float = Field(default=5.0, description="评分 (0-10)")
    issues: list[str] = Field(default_factory=list)
    verdict: str = Field(default="可行")


_score_parser = PydanticOutputParser(pydantic_object=ScoreResult)


async def call_llm(prompt: str, model: str | None = None, **kwargs: Any) -> str:
    """异步调用 LLM — 使用 GatewayChatModel（LangChain 适配器）。

    Args:
        prompt: 输入提示词。
        model: 模型名。
        **kwargs: 额外参数（node 等）。

    Returns:
        LLM 返回文本。不可用时返回空字符串。
    """
    from app.llm_gateway.langchain_adapter import GatewayChatModel

    try:
        node = kwargs.pop("node", "")
        llm = GatewayChatModel(
            task_type="evaluation_scoring",
            layer="evaluation",
            node=node,
            default_model=model or "deepseek-chat",
        )
        resp = await llm.ainvoke(prompt)
        return resp.content if isinstance(resp.content, str) else str(resp)
    except Exception as exc:
        logger.warning("LLM 调用失败（evaluation）: %s", exc)
        return ""
