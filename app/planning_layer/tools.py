"""C2 — Planning Layer 工具函数。"""

from __future__ import annotations

from typing import Any


async def retrieve_knowledge(query: str, top_k: int = 5) -> Any:
    """调用块 B 的 RetrievalPipeline 检索相关知识。

    返回类型为 knowledge_layer.models.RetrievalContext（BaseModel），
    含 results/matched_entities/text_unit_evidence 等字段。

    Args:
        query: 检索查询。
        top_k: 返回结果数。

    Returns:
        检索结果上下文，不可用时返回空对象。
    """
    try:
        from app.knowledge_layer.models import RetrievalContext
        from app.knowledge_layer.pipeline import RetrievalPipeline

        pipeline = RetrievalPipeline()
        return await pipeline.retrieve(query, mode="hybrid", top_k=top_k)
    except Exception:
        # 当 Neo4j/PGVector 不可用时返回空结果
        from app.knowledge_layer.models import RetrievalContext

        return RetrievalContext(query=query)


async def call_llm_async(prompt: str, model: str | None = None, **kwargs: Any) -> str:
    """异步调用 LLM。

    Args:
        prompt: 输入提示词。
        model: 模型名。
        **kwargs: 额外参数。

    Returns:
        LLM 返回文本。LLM 不可用时返回空字符串。
    """
    from app.core.llm import llm_complete

    try:
        return await llm_complete(prompt, model=model, **kwargs)
    except Exception:
        return ""
