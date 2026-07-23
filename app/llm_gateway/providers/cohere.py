"""Cohere Provider（预留）。"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from app.llm_gateway.providers.base import BaseProvider
from contracts.models import ModelConfig

logger = get_logger("prd2tsd.provider")


class CohereProvider(BaseProvider):
    """Cohere Rerank Provider（预留）。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 CohereProvider。

        Args:
            config: 模型配置。
        """
        super().__init__(config)

    async def rerank(self, query: str, docs: list[str], model: str = "", **kwargs: Any) -> RerankResponse:
        """调用 Cohere Rerank API（预留实现）。

        Args:
            query: 查询。
            docs: 文档列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            RerankResponse。
        """
        logger.warning("CohereProvider 为预留实现，返回模拟排序")
        n = len(docs)
        scores = [1.0 - i * 0.1 for i in range(n)]
        indices = list(range(n))
        return RerankResponse(
            scores=scores,
            indices=indices,
            model=model or self.config.default_model,
            input_tokens=len(query) + sum(len(d) for d in docs),
        )

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """Cohere LLM 调用（预留）。

        Args:
            prompt: 输入提示词。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            LLMResponse。
        """
        logger.warning("CohereProvider.complete 为预留实现")
        return LLMResponse(content="[Cohere 预留实现]", model=model or self.config.default_model)

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """Cohere Embedding（预留）。

        Args:
            texts: 文本列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。
        """
        logger.warning("CohereProvider.embed 为预留实现")
        return EmbeddingResponse(embeddings=[[0.0]] * len(texts))
