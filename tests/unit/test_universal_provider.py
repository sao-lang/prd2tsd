"""统一 Provider 门面协议选择测试。"""

from __future__ import annotations

import pytest

from app.llm_gateway.providers import ProviderFactory, UniversalProvider
from app.llm_gateway.providers.anthropic import AnthropicProvider
from app.llm_gateway.providers.openai import OpenAIProvider
from contracts.models import ModelConfig, ProviderType


@pytest.mark.asyncio
async def test_openai_compatible_vendors_share_one_provider_facade() -> None:
    """OpenAI-compatible 厂商应复用统一门面和同一协议适配器。"""
    config = ModelConfig(
        provider=ProviderType.DEEPSEEK,
        api_key="test-key",
        base_url="https://example.invalid/v1",
    )
    provider = ProviderFactory().create(ProviderType.DEEPSEEK, config)

    assert isinstance(provider, UniversalProvider)
    assert isinstance(provider._adapter, OpenAIProvider)
    await provider._adapter._client.close()


@pytest.mark.asyncio
async def test_custom_provider_can_select_anthropic_protocol() -> None:
    """自定义端点可用 protocol 配置选择非 OpenAI 协议。"""
    config = ModelConfig(
        provider=ProviderType.CUSTOM,
        base_url="https://example.invalid/v1",
        config={"protocol": "anthropic"},
    )
    provider = ProviderFactory().create("private-vendor", config)

    assert isinstance(provider, UniversalProvider)
    assert provider.protocol == "anthropic"
    assert isinstance(provider._adapter, AnthropicProvider)
    await provider._adapter._client.aclose()


def test_unknown_protocol_is_rejected() -> None:
    """未知协议应尽早失败并返回明确配置错误。"""
    config = ModelConfig(provider=ProviderType.CUSTOM, config={"protocol": "unknown"})

    with pytest.raises(ValueError, match="不支持的 Provider 协议"):
        ProviderFactory().create(ProviderType.CUSTOM, config)
