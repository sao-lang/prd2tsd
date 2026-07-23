"""Provider 抽象层 — 多模型供应商统一调用接口。"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from app.core.logger import get_logger
from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from contracts.models import ModelConfig, ProviderType

logger = get_logger("prd2tsd.provider")


class BaseProvider:
    """Provider 抽象基类。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 Provider。

        Args:
            config: 模型配置。
        """
        self.config = config

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 LLM 生成文本。子类必须实现。

        Args:
            prompt: 输入提示词。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            LLMResponse。
        """
        raise NotImplementedError

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """调用 Embedding 模型。子类必须实现。

        Args:
            texts: 文本列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            EmbeddingResponse。
        """
        raise NotImplementedError

    async def rerank(self, query: str, docs: list[str], model: str = "", **kwargs: Any) -> RerankResponse:
        """调用 Rerank 模型。子类必须实现。

        Args:
            query: 查询。
            docs: 文档列表。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            RerankResponse。
        """
        raise NotImplementedError


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
        # OpenAI 无原生 Rerank API，此处返回等权重
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
        # 简化版成本估算
        rates = {
            "deepseek-chat": (0.0005, 0.002),
            "gpt-4o-mini": (0.00015, 0.0006),
            "gpt-4o": (0.005, 0.015),
            "text-embedding-3-small": (0.00002, 0.0),
        }
        rate = rates.get(model, (0.001, 0.002))
        return (prompt_tokens * rate[0] + completion_tokens * rate[1]) / 1000


class AnthropicProvider(BaseProvider):
    """Anthropic Claude Provider（预留）。"""

    def __init__(self, config: ModelConfig) -> None:
        """初始化 AnthropicProvider。

        Args:
            config: 模型配置。
        """
        super().__init__(config)

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """调用 Claude API（预留实现）。

        Args:
            prompt: 输入提示词。
            model: 模型名。
            **kwargs: 额外参数。

        Returns:
            LLMResponse。
        """
        logger.warning("AnthropicProvider 为预留实现")
        return LLMResponse(content="[Anthropic 预留实现]", model=model or self.config.default_model)


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


class ProviderFactory:
    """Provider 工厂 — 根据供应商类型创建对应的 Provider。"""

    def create(self, provider_type: ProviderType | str, config: ModelConfig) -> BaseProvider:
        """创建 Provider 实例。

        Args:
            provider_type: 供应商类型。
            config: 模型配置。

        Returns:
            BaseProvider 实例。

        Raises:
            ValueError: 不支持的供应商类型时抛出。
        """
        if isinstance(provider_type, str):
            try:
                provider_type = ProviderType(provider_type)
            except ValueError:
                provider_type = ProviderType.CUSTOM

        providers = {
            ProviderType.OPENAI: OpenAIProvider,
            ProviderType.DEEPSEEK: OpenAIProvider,
            ProviderType.AZURE_OPENAI: OpenAIProvider,
            ProviderType.ANTHROPIC: AnthropicProvider,
            ProviderType.COHERE: CohereProvider,
            ProviderType.CUSTOM: CustomProvider,
        }

        provider_cls = providers.get(provider_type)
        if provider_cls is None:
            raise ValueError(f"不支持的供应商类型: {provider_type}")

        return provider_cls(config)
