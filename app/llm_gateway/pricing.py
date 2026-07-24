"""模型定价常量 — 集中管理所有模型的每千 Token 价格。

所有成本估算统一引用此模块，避免定价表多处定义导致不一致。
"""

from __future__ import annotations

# {model_name: (input_price_per_1k, output_price_per_1k)}
# 价格单位：美元 / 1K tokens
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # LLM
    "deepseek-chat": (0.0005, 0.002),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.005, 0.015),
    # Embedding
    "text-embedding-3-small": (0.00002, 0.0),
    # Rerank
    "rerank-english-v3.0": (0.001, 0.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """估算模型调用成本。

    Args:
        model: 模型名。
        input_tokens: 输入 Token 数。
        output_tokens: 输出 Token 数。

    Returns:
        估算成本（美元）。
    """
    rate = MODEL_PRICING.get(model, (0.001, 0.002))
    return (input_tokens * rate[0] + output_tokens * rate[1]) / 1000
