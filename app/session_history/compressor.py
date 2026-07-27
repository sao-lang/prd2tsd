"""上下文压缩器 — Token 超限时自动压缩。

压缩策略（按优先级）：
1. summarize: 对最旧的消息做 LLM 摘要（保留语义）
2. rolling:   丢弃最旧的消息（保留最新 N 轮）
3. truncate:  直接截断最早的消息文本
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.compressor")


class ChatMessage:
    """聊天消息。"""

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


class ContextCompressor:
    """上下文压缩器 — Token 超限时自动压缩。"""

    def __init__(self, llm_gateway: Any = None) -> None:
        """初始化压缩器。

        Args:
            llm_gateway: LLM Gateway 实例（可选，用于 summarize 策略）。
        """
        self.gateway = llm_gateway
        self.strategy_order = ["summarize", "rolling", "truncate"]

    async def compress(
        self,
        messages: list[ChatMessage],
        max_tokens: int = 128_000,
        reserve_for_latest: int = 32_000,
    ) -> list[ChatMessage]:
        """压缩消息列表至 max_tokens 以内。

        Args:
            messages: 消息列表。
            max_tokens: 最大 Token 数。
            reserve_for_latest: 为最新内容保留的 Token 数。

        Returns:
            压缩后的消息列表。
        """
        total = self._estimate_tokens(messages)
        if total <= max_tokens:
            return messages

        # 分离"可压缩区"（旧消息）和"保护区"（最新消息）
        safe_tokens = 0
        protected: list[ChatMessage] = []
        compressible: list[ChatMessage] = []

        for msg in reversed(messages):
            tokens = self._estimate_tokens([msg])
            if safe_tokens + tokens <= reserve_for_latest:
                protected.insert(0, msg)
                safe_tokens += tokens
            else:
                compressible.insert(0, msg)

        # 对可压缩区依次尝试策略
        for strategy in self.strategy_order:
            compressed = await self._apply_strategy(strategy, compressible, max_tokens - safe_tokens)
            if self._estimate_tokens(compressed) <= max_tokens - safe_tokens:
                estimated = self._estimate_tokens(compressed + protected)
                logger.info("上下文压缩完成: strategy=%s, %d→%d tokens", strategy, total, estimated)
                return compressed + protected

        # 终极兜底：只保留最后 N 轮
        logger.warning("上下文压缩兜底: 仅保留最新 %d tokens", safe_tokens)
        return protected

    async def _apply_strategy(
        self,
        strategy: str,
        messages: list[ChatMessage],
        budget: int,
    ) -> list[ChatMessage]:
        """应用单一压缩策略。"""
        if strategy == "truncate":
            return self._truncate(messages, budget)
        elif strategy == "rolling":
            return self._rolling(messages, budget)
        elif strategy == "summarize":
            return await self._summarize(messages, budget)
        return messages

    async def _summarize(
        self,
        messages: list[ChatMessage],
        budget: int,
    ) -> list[ChatMessage]:
        """LLM 摘要压缩 — 将旧消息压缩为一段摘要。"""
        if not self.gateway or not messages:
            return messages

        prompt = f"""请将以下对话压缩为一段简洁的摘要，保留关键信息。要求：
- 保留所有决策和结论
- 保留重要的数据/数字
- 保留待办事项
- 摘要长度不超过 {budget // 4} 个 Token

对话内容：
{''.join(f'{m.role}: {m.content[:500]}' for m in messages[:20])}
"""
        try:
            resp = await self.gateway.complete(
                prompt=prompt,
                task_type="memory_compress",
                max_tokens=budget,
            )
            return [ChatMessage(role="system", content=f"[历史摘要] {resp.content}")]
        except Exception:
            return self._rolling(messages, budget)

    def _rolling(self, messages: list[ChatMessage], budget: int) -> list[ChatMessage]:
        """滑动窗口 — 从旧到新丢弃，直到满足预算。"""
        result: list[ChatMessage] = []
        tokens = 0
        for msg in reversed(messages):
            msg_tokens = self._estimate_tokens([msg])
            if tokens + msg_tokens <= budget:
                result.insert(0, msg)
                tokens += msg_tokens
            else:
                break
        return result

    @staticmethod
    def _truncate(messages: list[ChatMessage], budget: int) -> list[ChatMessage]:
        """截断 — 直接掐掉最旧消息的文本。"""
        result: list[ChatMessage] = []
        tokens = 0
        for msg in reversed(messages):
            text = msg.content
            while text and tokens + len(text) // 4 > budget:
                text = text[: len(text) // 2]
            if text:
                result.insert(0, ChatMessage(role=msg.role, content=text))
                tokens += len(text) // 4
        return result

    @staticmethod
    def _estimate_tokens(messages: list[ChatMessage]) -> int:
        """粗略估算 Token 数。"""
        total = 0
        for msg in messages:
            text = msg.content
            chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
            english = len(text) - chinese
            total += int(chinese * 1.5 + english * 0.25)
        return total
