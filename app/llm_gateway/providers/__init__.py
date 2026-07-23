"""Provider 抽象层 — 多模型供应商统一调用接口。"""

from __future__ import annotations

from app.llm_gateway.providers.anthropic import AnthropicProvider
from app.llm_gateway.providers.base import BaseProvider
from app.llm_gateway.providers.cohere import CohereProvider
from app.llm_gateway.providers.custom import CustomProvider
from app.llm_gateway.providers.openai import OpenAIProvider
from contracts.models import ModelConfig, ProviderType

__all__ = [
    "BaseProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "CohereProvider",
    "CustomProvider",
    "ProviderFactory",
]


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
