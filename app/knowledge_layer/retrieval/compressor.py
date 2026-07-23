"""上下文压缩 — 将检索结果压缩至最大 Token 限制内。"""

from __future__ import annotations

from app.core.logger import get_logger
from app.knowledge_layer.config import kn_config
from app.knowledge_layer.models import ScoredDoc

logger = get_logger("prd2tsd.knowledge.compressor")


class Compressor:
    """上下文压缩器。

    通过截断/摘要方式将检索结果压缩到 max_tokens 以内。
    """

    def __init__(self, max_tokens: int | None = None) -> None:
        """初始化压缩器。

        Args:
            max_tokens: 最大 Token 数。
        """
        self._max_tokens = max_tokens or kn_config.max_compress_tokens

    def compress(self, results: list[ScoredDoc]) -> list[ScoredDoc]:
        """压缩检索结果。

        Args:
            results: 排序后的检索结果。

        Returns:
            压缩后的结果列表。
        """
        compressed: list[ScoredDoc] = []
        total_tokens = 0

        for doc in results:
            doc_tokens = self._estimate_tokens(doc.text)

            if total_tokens + doc_tokens <= self._max_tokens:
                compressed.append(doc)
                total_tokens += doc_tokens
            else:
                # 截断最后一个文档
                remaining = self._max_tokens - total_tokens
                if remaining > 20:
                    truncated_text = self._truncate_text(doc.text, remaining)
                    doc.text = truncated_text
                    compressed.append(doc)
                break

        logger.debug(
            "压缩完成: %d -> %d docs, %d tokens",
            len(results),
            len(compressed),
            total_tokens,
        )
        return compressed

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """估算文本的 Token 数（中英文混合近似）。

        Args:
            text: 输入文本。

        Returns:
            估算的 Token 数。
        """
        # 中文约 1.5 tokens/字，英文约 0.25 tokens/字符
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 0.25) + 1

    @staticmethod
    def _truncate_text(text: str, target_tokens: int) -> str:
        """截断文本至目标 Token 数。

        Args:
            text: 输入文本。
            target_tokens: 目标 Token 数。

        Returns:
            截断后的文本。
        """
        if target_tokens <= 0:
            return ""

        chars_per_token = 2  # 近似值
        max_chars = target_tokens * chars_per_token
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."
