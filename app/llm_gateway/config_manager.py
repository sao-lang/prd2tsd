"""模型配置管理器 — 三级优先级、运行时动态更新、配置合并。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.config import settings
from contracts.models import (
    ModelConfig,
    ModelType,
    ProviderType,
    RoutingRule,
)


class ModelConfigManager:
    """模型配置管理器。

    管理所有模型类型的配置，支持三级优先级（API 注入 > 环境变量 > 默认值）。
    """

    def __init__(self) -> None:
        """初始化配置管理器。"""
        # 运行时配置（API 动态注入，最高优先级）
        self._runtime_config: dict[str, dict[str, dict[str, Any]]] = {}
        # 路由规则（运行时动态更新）
        self._runtime_routing: dict[str, dict[str, Any]] = {}

    def _get_env_config(self, model_type: str, provider: str) -> dict[str, Any]:
        """从环境变量中获取配置。

        Args:
            model_type: 模型类型。
            provider: 供应商名称。

        Returns:
            配置字典。
        """
        env = settings.get_model_config_env(model_type, provider)
        # 解析超时和重试（使用默认值）
        return {
            "api_key": env.get("api_key", ""),
            "base_url": env.get("base_url", ""),
            "default_model": env.get("default_model", ""),
            "timeout": 60,
            "max_retries": 3,
        }

    def _get_default_config(self, model_type: str, provider: str) -> dict[str, Any]:
        """获取代码默认配置。

        Args:
            model_type: 模型类型。
            provider: 供应商名称。

        Returns:
            默认配置字典。
        """
        defaults: dict[str, dict[str, Any]] = {
            "llm": {
                "deepseek": {
                    "api_key": "",
                    "base_url": "https://api.deepseek.com/v1",
                    "default_model": "deepseek-chat",
                    "timeout": 60,
                    "max_retries": 3,
                },
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-4o-mini",
                    "timeout": 60,
                    "max_retries": 3,
                },
            },
            "embedding": {
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "text-embedding-3-small",
                    "timeout": 60,
                    "max_retries": 3,
                },
            },
            "rerank": {
                "cohere": {
                    "api_key": "",
                    "base_url": "https://api.cohere.com/v1",
                    "default_model": "rerank-english-v3.0",
                    "timeout": 60,
                    "max_retries": 3,
                },
            },
            "judge": {
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-4o-mini",
                    "timeout": 60,
                    "max_retries": 3,
                },
            },
            "vision": {
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-4o",
                    "timeout": 60,
                    "max_retries": 3,
                },
            },
        }
        return deepcopy(defaults.get(model_type, {}).get(provider, {}))

    def get_config(self, model_type: ModelType | str, provider: str) -> ModelConfig:
        """获取某模型类型的完整配置（三级优先级合并）。

        Args:
            model_type: 模型类型。
            provider: 供应商名称。

        Returns:
            合并后的 ModelConfig。
        """
        type_str = model_type.value if isinstance(model_type, ModelType) else model_type

        # 优先级 3：默认值
        config = self._get_default_config(type_str, provider)

        # 优先级 2：环境变量覆盖
        env_config = self._get_env_config(type_str, provider)
        for key in ["api_key", "base_url", "default_model"]:
            if env_config.get(key):
                config[key] = env_config[key]

        # 优先级 1：运行时配置覆盖
        runtime = self._runtime_config.get(type_str, {}).get(provider, {})
        for key in ["api_key", "base_url", "default_model", "timeout", "max_retries"]:
            if key in runtime and runtime[key] is not None:
                config[key] = runtime[key]

        # 合并额外配置
        extra_config = {}
        if "config" in runtime and runtime["config"]:
            extra_config.update(runtime["config"])

        return ModelConfig(
            provider=ProviderType(provider) if provider in [p.value for p in ProviderType] else ProviderType.CUSTOM,
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url", ""),
            default_model=config.get("default_model", ""),
            config=extra_config,
            timeout=int(config.get("timeout", 60)),
            max_retries=int(config.get("max_retries", 3)),
        )

    def update_config(
        self,
        model_type: ModelType,
        provider: str,
        fields: dict[str, Any],
    ) -> None:
        """API 动态注入配置。

        Args:
            model_type: 模型类型。
            provider: 供应商名称。
            fields: 配置字段字典（部分更新）。
        """
        type_str = model_type.value if isinstance(model_type, ModelType) else model_type
        if type_str not in self._runtime_config:
            self._runtime_config[type_str] = {}
        if provider not in self._runtime_config[type_str]:
            self._runtime_config[type_str][provider] = {}

        # 部分更新：只覆盖提供的字段
        for key, value in fields.items():
            if value is not None:
                self._runtime_config[type_str][provider][key] = value

    def update_routing_rule(self, task_type: str, rule: RoutingRule) -> None:
        """更新路由规则。

        Args:
            task_type: 任务类型。
            rule: 路由规则。
        """
        self._runtime_routing[task_type] = rule.model_dump(exclude_none=True)

    def get_routing_rule(self, task_type: str) -> RoutingRule | None:
        """获取路由规则。

        Args:
            task_type: 任务类型。

        Returns:
            路由规则，不存在时返回 None。
        """
        # 先查运行时
        if task_type in self._runtime_routing:
            return RoutingRule(**self._runtime_routing[task_type])

        # 再查环境变量
        env_rules = settings.get_routing_env()
        if task_type.upper() in {k.upper().replace("-", "_") for k in env_rules}:
            normalized_key = next(
                k for k in env_rules
                if k.upper().replace("-", "_") == task_type.upper().replace("-", "_")
            )
            rule_data = env_rules[normalized_key]
            return RoutingRule(
                type=ModelType(rule_data.get("type", "llm")),
                provider=rule_data.get("provider", ""),
                model=rule_data.get("model", ""),
            )

        return None

    def resolve_model(self, task_type: str) -> tuple[ModelConfig, str]:
        """根据 task_type 解析出完整的 ModelConfig 和模型名。

        Args:
            task_type: 任务类型。

        Returns:
            (ModelConfig, model_name) 元组。
        """
        rule = self.get_routing_rule(task_type)
        if rule is None:
            # 默认使用 LLM DeepSeek
            rule = RoutingRule(type=ModelType.LLM, provider="deepseek", model="deepseek-chat")

        model_type = rule.type
        provider = rule.provider
        model_name = rule.model or ""

        config = self.get_config(model_type, provider)

        # 如果路由规则指定了模型名，覆盖默认模型
        if model_name:
            config.default_model = model_name

        return config, config.default_model

    def reset_to_env(self) -> None:
        """清除运行时配置，恢复到环境变量配置。"""
        self._runtime_config.clear()
        self._runtime_routing.clear()
