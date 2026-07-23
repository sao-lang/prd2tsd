"""模型配置相关请求/响应 Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contracts.models import ModelType


class ModelConfigResponse(BaseModel):
    """模型配置响应（API Key 已掩码）。"""

    provider: str
    api_key: str = "****"
    base_url: str = ""
    default_model: str = ""
    timeout: int = 60
    max_retries: int = 3
    config: dict[str, Any] = Field(default_factory=dict)


class ModelConfigUpdateRequest(BaseModel):
    """模型配置更新请求。"""

    type: ModelType
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    timeout: int | None = None
    max_retries: int | None = None
    config: dict[str, Any] | None = None


class RoutingRuleUpdateRequest(BaseModel):
    """路由规则更新请求。"""

    task_type: str
    type: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
