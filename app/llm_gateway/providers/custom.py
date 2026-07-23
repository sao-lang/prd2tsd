"""自定义 Provider — 兼容任意 OpenAI-API 格式的服务。"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.core.logger import get_logger
from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from app.llm_gateway.providers.base import BaseProvider
from contracts.models import ModelConfig

logger = get_logger("prd2tsd.provider")


class CustomProvider(BaseProvider):
    """自定义 Provider — 兼容任意 OpenAI-API 格式的服务。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 CustomProvider。

        Args:
            config: 模型配置。
        """
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用自定义 API。

        Args:
            prompt: 输入提示词。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            LLMResponse。
        """
        model_name = model or self.config.default_model
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 4096)

        response = await self._client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=model_name,
            input_tokens=0,
            output_tokens=0,
        )

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """自定义 Embedding（预留）。

        Args:
            texts: 文本列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。
        """
        logger.warning("CustomProvider.embed 为预留实现")
        return EmbeddingResponse(embeddings=[[0.0]] * len(texts))

    async def rerank(self, query: str, docs: list[str], model: str = "", **kwargs: Any) -> RerankResponse:
        """自定义 Rerank（预留）。

        Args:
            query: 查询。
            docs: 文档列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            RerankResponse。
        """
        logger.warning("CustomProvider.rerank 为预留实现")
        n = len(docs)
        return RerankResponse(scores=[1.0] * n, indices=list(range(n)))
