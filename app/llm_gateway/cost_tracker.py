"""成本追踪器 — 记录每次 LLM 调用的 token 和 cost。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class CostRecord:
    """单次调用的成本记录。"""

    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


class CostTracker:
    """成本追踪器。

    记录每次模型调用的 input_tokens / output_tokens / cost。
    """

    def __init__(self) -> None:
        """初始化成本追踪器。"""
        self._records: list[CostRecord] = []

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        metadata: dict[str, Any] | None = None,
    ) -> CostRecord:
        """记录一次模型调用的成本。

        Args:
            model: 模型名。
            input_tokens: 输入 Token 数。
            output_tokens: 输出 Token 数。
            metadata: 额外元数据。

        Returns:
            创建的成本记录。
        """
        cost = self._estimate_cost(model, input_tokens, output_tokens)
        record = CostRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            metadata=metadata or {},
        )
        self._records.append(record)
        return record

    def get_total_cost(self) -> float:
        """获取总成本。

        Returns:
            累计成本（美元）。
        """
        return sum(r.cost for r in self._records)

    def get_total_tokens(self) -> int:
        """获取总 Token 数。

        Returns:
            累计 Token 数。
        """
        return sum(r.input_tokens + r.output_tokens for r in self._records)

    def get_records(self, limit: int = 100) -> list[CostRecord]:
        """获取最近的成本记录。

        Args:
            limit: 返回记录数量上限。

        Returns:
            成本记录列表，按时间倒序。
        """
        return sorted(self._records, key=lambda r: r.timestamp, reverse=True)[:limit]

    def clear(self) -> None:
        """清除所有成本记录。"""
        self._records.clear()

    @staticmethod
    def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """估算模型调用成本。

        Args:
            model: 模型名。
            input_tokens: 输入 Token 数。
            output_tokens: 输出 Token 数。

        Returns:
            估算成本（美元）。
        """
        # 按模型分级的每千 Token 价格（$ / 1K tokens）
        pricing: dict[str, tuple[float, float]] = {
            "deepseek-chat": (0.0005, 0.002),
            "gpt-4o-mini": (0.00015, 0.0006),
            "gpt-4o": (0.005, 0.015),
            "text-embedding-3-small": (0.00002, 0.0),
            "rerank-english-v3.0": (0.001, 0.0),
        }

        rate = pricing.get(model, (0.001, 0.002))
        return (input_tokens * rate[0] + output_tokens * rate[1]) / 1000
