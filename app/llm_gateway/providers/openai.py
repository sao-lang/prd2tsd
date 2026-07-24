"""OpenAI 兼容 Provider — 兼容 OpenAI / DeepSeek / Azure OpenAI。"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.core.logger import get_logger
from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from app.llm_gateway.providers.base import BaseProvider
from contracts.models import ModelConfig

logger = get_logger("prd2tsd.provider")


class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 Provider — 兼容 OpenAI / DeepSeek / Azure OpenAI。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 OpenAIProvider。

        Args:
            config: 模型配置（含 api_key, base_url 等）。
        """
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 OpenAI 兼容的 Chat Completion API。

        Args:
            prompt: 输入提示词。
            model: 模型名。为空时使用配置的默认模型。
            **kwargs: 额外参数（temperature, max_tokens 等）。

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
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=model_name,
            cost=self._calculate_cost(usage.prompt_tokens, usage.completion_tokens, model_name),
            input_tokens=usage.prompt_tokens or 0,
            output_tokens=usage.completion_tokens or 0,
        )

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """调用 OpenAI 兼容的 Embedding API。

        Args:
            texts: 文本列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。
        """
        model_name = model or self.config.default_model
        response = await self._client.embeddings.create(
            model=model_name,
            input=texts,
            **kwargs,
        )

        embeddings = [item.embedding for item in response.data]
        usage = response.usage

        return EmbeddingResponse(
            embeddings=embeddings,
            model=model_name,
            input_tokens=usage.prompt_tokens or 0,
            cost=self._calculate_cost(usage.prompt_tokens, 0, model_name),
        )

    async def rerank(self, query: str, docs: list[str], model: str = "", **kwargs: Any) -> RerankResponse:
        """OpenAI Provider 暂不支持 Rerank，通过模拟返回。

        Args:
            query: 查询。
            docs: 文档列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            RerankResponse（模拟）。
        """
        logger.warning("OpenAIProvider.rerank 为模拟实现，返回等权重排序")
        n = len(docs)
        scores = [1.0 - i * 0.1 for i in range(n)]
        indices = list(range(n))
        return RerankResponse(
            scores=scores,
            indices=indices,
            model=model or self.config.default_model,
            input_tokens=len(query) + sum(len(d) for d in docs),
        )

    @staticmethod
    def _calculate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """估算调用成本。

        Args:
            prompt_tokens: 输入 Token 数。
            completion_tokens: 输出 Token 数。
            model: 模型名。

        Returns:
            估算成本（美元）。
        """
        from app.llm_gateway.pricing import estimate_cost
        return estimate_cost(model, prompt_tokens, completion_tokens)
