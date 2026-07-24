"""成本追踪器 — 记录每次 LLM 调用的 token 和 cost。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
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
        self._lock = Lock()

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
        from app.llm_gateway.pricing import estimate_cost as _calc_cost
        cost = _calc_cost(model, input_tokens, output_tokens)
        with self._lock:
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
        with self._lock:
            return sum(r.cost for r in self._records)

    def get_total_tokens(self) -> int:
        """获取总 Token 数。

        Returns:
            累计 Token 数。
        """
        with self._lock:
            return sum(r.input_tokens + r.output_tokens for r in self._records)

    def get_records(self, limit: int = 100) -> list[CostRecord]:
        """获取最近的成本记录。

        Args:
            limit: 返回记录数量上限。

        Returns:
            成本记录列表，按时间倒序。
        """
        with self._lock:
            sorted_records = sorted(self._records, key=lambda r: r.timestamp, reverse=True)[:limit]
        return sorted_records

    def clear(self) -> None:
        """清除所有成本记录。"""
        with self._lock:
            self._records.clear()
