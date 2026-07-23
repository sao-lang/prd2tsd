"""模型配置管理路由 — GET/PUT/DELETE 各类模型配置和路由规则。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.schemas.model_config import (
    ModelConfigUpdateRequest,
    RoutingRuleUpdateRequest,
)
from app.llm_gateway import config_manager as global_config_manager
from app.llm_gateway.config_manager import ModelConfigManager
from contracts.models import ModelType, RoutingRule

router = APIRouter(prefix="/api/v1/model-config", tags=["model-config"])


def get_config_manager() -> ModelConfigManager:
    """获取模型配置管理器。

    Returns:
        ModelConfigManager 实例。
    """
    return global_config_manager


@router.get("")
async def get_all_configs(
    type: str | None = Query(None, description="模型类型（llm/embedding/rerank/judge/vision）"),
    provider: str | None = Query(None, description="供应商名称"),
    cm: ModelConfigManager = Depends(get_config_manager),
) -> dict[str, Any]:
    """查询当前所有模型配置（API Key 自动掩码）。

    Args:
        type: 可选的模型类型过滤。
        provider: 可选的供应商过滤。
        cm: 模型配置管理器。

    Returns:
        所有模型配置的字典，API Key 已掩码。
    """
    if type and provider:
        config = cm.get_config(ModelType(type), provider)
        return {
            "provider": config.provider.value,
            "api_key": config.masked_api_key(),
            "base_url": config.base_url,
            "default_model": config.default_model,
            "timeout": config.timeout,
            "max_retries": config.max_retries,
        }

    # 返回所有模型类型的配置
    result: dict[str, Any] = {}
    model_types = ["llm", "embedding", "rerank", "judge", "vision"]
    providers_map = {
        "llm": ["deepseek", "openai"],
        "embedding": ["openai"],
        "rerank": ["cohere"],
        "judge": ["openai"],
        "vision": ["openai"],
    }

    for mt in model_types:
        if type and mt != type:
            continue
        result[mt] = {}
        for prov in providers_map.get(mt, []):
            if provider and prov != provider:
                continue
            config = cm.get_config(ModelType(mt), prov)
            result[mt][prov] = {
                "provider": config.provider.value,
                "api_key": config.masked_api_key(),
                "base_url": config.base_url,
                "default_model": config.default_model,
                "timeout": config.timeout,
                "max_retries": config.max_retries,
            }

    result["routing_rules"] = {}
    for task_type in [
        "analysis.requirement",
        "analysis.constraint",
        "planning.architecture",
        "evaluation.scoring",
        "embedding",
        "rerank",
    ]:
        rule = cm.get_routing_rule(task_type)
        if rule:
            result["routing_rules"][task_type] = rule.model_dump()

    return result


@router.put("")
async def update_config(
    req: ModelConfigUpdateRequest,
    cm: ModelConfigManager = Depends(get_config_manager),
) -> dict[str, str]:
    """修改模型配置（API 动态注入，立即生效）。

    Args:
        req: 配置更新请求。
        cm: 模型配置管理器。

    Returns:
        操作结果消息。
    """
    fields: dict[str, Any] = {}
    if req.api_key is not None:
        fields["api_key"] = req.api_key
    if req.base_url is not None:
        fields["base_url"] = req.base_url
    if req.default_model is not None:
        fields["default_model"] = req.default_model
    if req.timeout is not None:
        fields["timeout"] = req.timeout
    if req.max_retries is not None:
        fields["max_retries"] = req.max_retries
    if req.config is not None:
        fields["config"] = req.config

    cm.update_config(req.type, req.provider, fields)
    return {"message": f"{req.type.value}/{req.provider} 配置已更新"}


@router.put("/routing")
async def update_routing_rule(
    req: RoutingRuleUpdateRequest,
    cm: ModelConfigManager = Depends(get_config_manager),
) -> dict[str, str]:
    """修改路由规则。

    Args:
        req: 路由规则更新请求。
        cm: 模型配置管理器。

    Returns:
        操作结果消息。
    """
    rule_fields: dict[str, Any] = {}
    if req.type is not None:
        rule_fields["type"] = ModelType(req.type)
    if req.provider is not None:
        rule_fields["provider"] = req.provider
    if req.model is not None:
        rule_fields["model"] = req.model
    if req.temperature is not None:
        rule_fields["temperature"] = req.temperature
    if req.max_tokens is not None:
        rule_fields["max_tokens"] = req.max_tokens

    rule = RoutingRule(**rule_fields)
    cm.update_routing_rule(req.task_type, rule)
    return {"message": f"路由规则 {req.task_type} 已更新"}


@router.delete("/runtime")
async def reset_runtime_config(
    cm: ModelConfigManager = Depends(get_config_manager),
) -> dict[str, str]:
    """重置运行时配置（恢复到环境变量配置）。

    Args:
        cm: 模型配置管理器。

    Returns:
        操作结果消息。
    """
    cm.reset_to_env()
    return {"message": "运行时配置已清除，已恢复到环境变量配置"}
