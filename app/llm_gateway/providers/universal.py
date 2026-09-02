"""统一 Provider 门面 — 以协议能力而非厂商名称暴露 Gateway 接口。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from app.llm_gateway.models import EmbeddingResponse, LLMResponse, RerankResponse
from app.llm_gateway.providers.anthropic import AnthropicProvider
from app.llm_gateway.providers.base import BaseProvider
from app.llm_gateway.providers.cohere import CohereProvider
from app.llm_gateway.providers.openai import OpenAIProvider
from contracts.models import ModelConfig, ProviderType


class UniversalProvider(BaseProvider):
    """根据端点协议选择内部适配器的统一 Provider。

    DeepSeek、OpenAI、Azure OpenAI 及自建 OpenAI-compatible 服务复用同一协议；
    Anthropic Messages 和 Cohere V2 仅在内部保留必要的协议适配。
    """

    def __init__(self, config: ModelConfig) -> None:
        """根据显式 protocol 或 Provider 类型创建协议适配器。"""
        super().__init__(config)
        protocol = str(config.config.get("protocol", "")).strip().lower()
        if not protocol:
            protocol = {
                ProviderType.ANTHROPIC: "anthropic",
                ProviderType.COHERE: "cohere",
            }.get(config.provider, "openai")
        adapters: dict[str, type[BaseProvider]] = {
            "openai": OpenAIProvider,
            "openai_compatible": OpenAIProvider,
            "anthropic": AnthropicProvider,
            "cohere": CohereProvider,
        }
        adapter_type = adapters.get(protocol)
        if adapter_type is None:
            raise ValueError(f"不支持的 Provider 协议: {protocol}")
        self.protocol = protocol
        self._adapter = adapter_type(config)

    async def complete(self, prompt: str, model: str = "", **kwargs: Any) -> LLMResponse:
        """统一文本生成。"""
        return await self._adapter.complete(prompt, model, **kwargs)

    async def stream_complete(
        self,
        prompt: str,
        model: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """统一流式文本生成。"""
        async for chunk in self._adapter.stream_complete(prompt, model, **kwargs):
            yield chunk

    async def embed(self, texts: list[str], model: str = "", **kwargs: Any) -> EmbeddingResponse:
        """统一文本向量化。"""
        return await self._adapter.embed(texts, model, **kwargs)

    async def rerank(
        self,
        query: str,
        docs: list[str],
        model: str = "",
        **kwargs: Any,
    ) -> RerankResponse:
        """统一文档重排。"""
        return await self._adapter.rerank(query, docs, model, **kwargs)
