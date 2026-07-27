"""记忆检索器 — 多策略融合检索。

支持三种策略：
1. Recency（最近优先）— 适用于短期对话
2. Relevance（语义相关）— 适用于知识问答
3. Importance（重要优先）— 适用于长期记忆
4. Hybrid（融合检索）— 三种策略加权融合
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from contracts.models import MemoryItem


class MemoryRetriever:
    """记忆检索器 — 多策略融合检索。"""

    def __init__(self, vector_store: Any = None, llm_gateway: Any = None) -> None:
        """初始化记忆检索器。

        Args:
            vector_store: 向量存储实例（可选）。
            llm_gateway: LLM Gateway 实例（可选）。
        """
        self.vector_store = vector_store
        self.gateway = llm_gateway

    async def retrieve(
        self,
        query: str,
        messages: list[dict[str, str]],
        strategy: str = "hybrid",
        top_k: int = 10,
    ) -> list[MemoryItem]:
        """检索历史记忆。

        Args:
            query: 当前查询。
            messages: 会话消息列表。
            strategy: 检索策略（recency / relevance / importance / hybrid）。
            top_k: 返回数量。

        Returns:
            按综合评分排序的记忆条目。
        """
        items: list[MemoryItem] = []
        for msg in messages:
            item = MemoryItem(
                content=msg.get("content", ""),
                role=msg.get("role", "user"),
                timestamp=datetime.now(UTC),
            )
            item.recency_score = self._score_recency(item.timestamp)

            if strategy in ("relevance", "hybrid"):
                item.relevance_score = await self._score_relevance(query, item.content)

            if strategy in ("importance", "hybrid"):
                item.importance_score = await self._score_importance(item.content)

            item.composite_score = self._compute_composite(item, strategy)
            items.append(item)

        items.sort(key=lambda x: x.composite_score, reverse=True)
        return items[:top_k]

    @staticmethod
    def _score_recency(timestamp: datetime) -> float:
        """时效性评分 — 越新越高（指数衰减）。"""
        hours_ago = (datetime.now(UTC) - timestamp).total_seconds() / 3600
        return math.exp(-hours_ago / 24)  # 24 小时半衰期

    async def _score_relevance(self, query: str, content: str) -> float:
        """相关性评分 — 向量语义相似度或关键词重叠。"""
        if not content:
            return 0.0
        q_words = set(query.lower().split())
        c_words = set(content.lower().split())
        overlap = len(q_words & c_words)
        return overlap / max(len(q_words), 1) if q_words else 0.0

    async def _score_importance(self, content: str) -> float:
        """重要性评分 — LLM 判断或默认值。"""
        if not self.gateway or not content:
            return 0.5
        prompt = f"""判断以下信息的重要性（0-1）：
- 0.0: 闲聊、问候
- 0.3: 一般信息
- 0.6: 决策、需求、约束
- 0.8: 用户明确指示的重要信息
- 1.0: 安全/合规相关的关键信息

内容：{content[:300]}
只返回一个 0-1 之间的数字。"""
        try:
            resp = await self.gateway.complete(
                prompt=prompt,
                task_type="memory_importance",
                max_tokens=10,
            )
            return max(0.0, min(1.0, float(resp.content.strip())))
        except Exception:
            return 0.5

    @staticmethod
    def _compute_composite(item: MemoryItem, strategy: str) -> float:
        """综合评分 — 按策略加权。"""
        weights = {
            "recency": {"recency": 1.0, "relevance": 0.0, "importance": 0.0},
            "relevance": {"recency": 0.0, "relevance": 1.0, "importance": 0.0},
            "importance": {"recency": 0.0, "relevance": 0.0, "importance": 1.0},
            "hybrid": {"recency": 0.3, "relevance": 0.4, "importance": 0.3},
        }
        w = weights.get(strategy, weights["hybrid"])
        return (
            item.recency_score * w["recency"]
            + item.relevance_score * w["relevance"]
            + item.importance_score * w["importance"]
        )
