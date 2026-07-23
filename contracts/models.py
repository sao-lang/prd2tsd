"""跨 Layer 数据模型 — 所有模型调用方统一使用。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ModelType(StrEnum):
    """模型类型枚举 — 涵盖所有模型调用场景。"""

    LLM = "llm"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    JUDGE = "judge"
    VISION = "vision"
    AUDIO = "audio"
    IMAGE = "image"


class ProviderType(StrEnum):
    """支持的模型供应商。"""

    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    AZURE_OPENAI = "azure_openai"
    COHERE = "cohere"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


class ModelConfig(BaseModel):
    """单个模型的完整配置 — 所有模型调用方统一使用此结构。"""

    provider: ProviderType = ProviderType.OPENAI
    api_key: str = ""
    base_url: str = ""
    default_model: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    timeout: int = 60
    max_retries: int = 3

    def masked_api_key(self) -> str:
        """返回掩码后的 API Key，用于日志和 API 响应。

        Returns:
            掩码后的 Key，例如 "sk-a***f456"。
        """
        if not self.api_key or len(self.api_key) < 8:
            return "****"
        return self.api_key[:4] + "****" + self.api_key[-4:]


class ModelEndpointConfig(BaseModel):
    """某模型类型的完整配置（支持多供应商、多模型）。"""

    type: ModelType
    providers: dict[str, ModelConfig] = Field(default_factory=dict)
    default_provider: str = ""
    default_model: str = ""


class RoutingRule(BaseModel):
    """模型路由规则 — task_type → 模型映射。"""

    type: ModelType = ModelType.LLM
    provider: str = ""
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class FullModelConfig(BaseModel):
    """完整模型配置（所有类型 + 路由规则）。"""

    endpoints: dict[ModelType, ModelEndpointConfig] = Field(default_factory=dict)
    routing_rules: dict[str, RoutingRule] = Field(default_factory=dict)


class ModelConfigUpdate(BaseModel):
    """模型配置更新请求体（API 动态注入用）。"""

    type: ModelType
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    config: dict[str, Any] | None = None
    timeout: int | None = None
    max_retries: int | None = None


class RoutingRuleUpdate(BaseModel):
    """路由规则更新请求体（API 动态注入用）。"""

    task_type: str
    type: ModelType | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    config: dict[str, Any] | None = None
