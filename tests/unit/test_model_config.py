"""模型配置单元测试 — 三级优先级/路由/动态更新/Key 掩码。"""

from __future__ import annotations

import pytest

from app.llm_gateway.config_manager import ModelConfigManager
from contracts.models import ModelConfig, ModelType, RoutingRule


@pytest.fixture
def manager() -> ModelConfigManager:
    """创建测试用配置管理器。"""
    return ModelConfigManager()


def test_masked_api_key():
    """验证 API Key 掩码函数正确。"""
    config = ModelConfig(api_key="sk-abcdef1234567890")
    masked = config.masked_api_key()
    assert "sk-a" in masked and "7890" in masked
    assert "sk-abcdef" not in masked
    assert "****" in masked


def test_masked_short_key():
    """验证短 Key 掩码。"""
    config = ModelConfig(api_key="sk-a")
    assert config.masked_api_key() == "****"


def test_config_priority_default(manager: ModelConfigManager):
    """验证默认配置存在。"""
    config = manager.get_config(ModelType.LLM, "deepseek")
    assert config.provider.value == "deepseek"
    assert config.base_url == "https://api.deepseek.com/v1"
    assert config.default_model == "deepseek-chat"
    assert config.timeout == 60
    assert config.max_retries == 3


def test_routing_rule_creation():
    """验证路由规则创建。"""
    rule = RoutingRule(
        type=ModelType.LLM,
        provider="deepseek",
        model="deepseek-chat",
        temperature=0.7,
    )
    assert rule.type == ModelType.LLM
    assert rule.provider == "deepseek"
    assert rule.model == "deepseek-chat"
    assert rule.temperature == 0.7


def test_routing_default_rule(manager: ModelConfigManager):
    """验证默认路由规则（通过 resolve_model 兜底）。"""
    config, model = manager.resolve_model("analysis.requirement")
    assert config is not None
    assert model is not None


def test_dynamic_routing_update(manager: ModelConfigManager):
    """验证运行时修改路由规则后立即生效。"""
    manager.update_routing_rule(
        "analysis.requirement",
        RoutingRule(type=ModelType.LLM, provider="openai", model="gpt-4o"),
    )
    config, model_name = manager.resolve_model("analysis.requirement")
    assert config.provider.value == "openai"
    assert model_name == "gpt-4o"


def test_config_merge_partial_update(manager: ModelConfigManager):
    """验证部分更新时未提供的字段保留原值。"""
    original = manager.get_config(ModelType.LLM, "deepseek")
    manager.update_config(ModelType.LLM, "deepseek", {"api_key": "sk-new"})
    updated = manager.get_config(ModelType.LLM, "deepseek")
    assert updated.api_key == "sk-new"
    assert updated.base_url == original.base_url
    assert updated.default_model == original.default_model


def test_reset_runtime_config(manager: ModelConfigManager):
    """验证清除运行时配置后恢复。"""
    manager.update_config(ModelType.LLM, "deepseek", {"api_key": "sk-runtime"})
    config_before = manager.get_config(ModelType.LLM, "deepseek")
    assert config_before.api_key == "sk-runtime"

    manager.reset_to_env()
    config_after = manager.get_config(ModelType.LLM, "deepseek")
    assert config_after.api_key != "sk-runtime"


def test_resolve_model(manager: ModelConfigManager):
    """验证 task_type → ModelConfig 解析。"""
    config, model_name = manager.resolve_model("analysis.requirement")
    assert config is not None
    assert model_name is not None


def test_all_model_types(manager: ModelConfigManager):
    """验证所有模型类型均可获取配置。"""
    for mt in [ModelType.LLM, ModelType.EMBEDDING, ModelType.RERANK,
               ModelType.JUDGE, ModelType.VISION]:
        providers = {
            "llm": "deepseek", "embedding": "openai",
            "rerank": "cohere", "judge": "openai", "vision": "openai",
        }
        prov = providers.get(mt.value, "openai")
        config = manager.get_config(mt, prov)
        assert config is not None
