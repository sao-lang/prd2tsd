"""模型配置管理器 — 三级优先级、运行时动态更新、配置合并。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from contracts.models import (
    DefaultModel,
    ModelConfig,
    ModelPurpose,
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
        self._file_config = self._load_file_config()

    @staticmethod
    def _load_file_config() -> dict[str, Any]:
        """加载可选 YAML 配置；缺失文件等价于空配置。"""
        path = Path(settings.MODEL_ROUTING_CONFIG_FILE)
        if not path.is_file():
            return {}
        with path.open(encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"模型路由配置根节点必须是对象: {path}")
        return loaded

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
            "timeout": env.get("timeout", 60),
            "max_retries": env.get("max_retries", 3),
            "protocol": env.get("protocol", ""),
        }

    def _get_file_provider_config(self, model_type: str, provider: str) -> dict[str, Any]:
        """读取 YAML 中的 Provider 配置。"""
        providers = self._file_config.get("providers", {})
        if not isinstance(providers, dict):
            return {}
        by_type = providers.get(model_type, {})
        if not isinstance(by_type, dict):
            return {}
        config = by_type.get(provider, {})
        return deepcopy(config) if isinstance(config, dict) else {}

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
                "anthropic": {
                    "api_key": "",
                    "base_url": "https://api.anthropic.com/v1",
                    "default_model": "claude-sonnet-4-6",
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
                    "base_url": "https://api.cohere.com/v2",
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

        # 优先级 2.5：YAML 配置文件覆盖代码默认值
        file_config = self._get_file_provider_config(type_str, provider)
        for key in ["api_key", "base_url", "default_model", "timeout", "max_retries"]:
            if key in file_config and file_config[key] not in (None, ""):
                config[key] = file_config[key]

        # 优先级 2：环境变量覆盖
        env_config = self._get_env_config(type_str, provider)
        for key in ["api_key", "base_url", "default_model", "timeout", "max_retries"]:
            if env_config.get(key):
                config[key] = env_config[key]

        # 优先级 1：运行时配置覆盖
        runtime = self._runtime_config.get(type_str, {}).get(provider, {})
        for key in ["api_key", "base_url", "default_model", "timeout", "max_retries"]:
            if key in runtime and runtime[key] is not None:
                config[key] = runtime[key]

        # 合并额外配置
        extra_config = {}
        if isinstance(file_config.get("config"), dict):
            extra_config.update(file_config["config"])
        if file_config.get("protocol"):
            extra_config["protocol"] = file_config["protocol"]
        protocol = env_config.get("protocol")
        if protocol:
            extra_config["protocol"] = protocol
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
        candidates = self._routing_candidates(task_type)

        # 先查运行时：精确任务优先，随后回退到所属层。
        for candidate in candidates:
            if candidate in self._runtime_routing:
                return RoutingRule(**self._runtime_routing[candidate])

        # 再查环境变量
        env_rules = settings.get_routing_env()
        normalized_env = {key.replace("-", "_").replace(".", "_").lower(): value for key, value in env_rules.items()}
        for candidate in candidates:
            rule_data = normalized_env.get(candidate.replace("-", "_").replace(".", "_").lower())
            if rule_data:
                return RoutingRule(
                    type=ModelType(rule_data.get("type", "llm")),
                    provider=rule_data.get("provider", ""),
                    model=rule_data.get("model", ""),
                )

        # YAML 路由低于环境变量、高于代码默认值。
        file_rules = self._file_config.get("routing", {})
        if isinstance(file_rules, dict):
            for candidate in candidates:
                file_rule_data = file_rules.get(candidate)
                if isinstance(file_rule_data, dict):
                    return RoutingRule.model_validate(file_rule_data)

        return None

    @staticmethod
    def _routing_candidates(task_type: str) -> list[str]:
        """构造从精确任务到模型用途的路由候选键。"""
        normalized = task_type.strip().lower().replace("-", "_") or ModelPurpose.DEFAULT.value
        purpose = normalized.split(".", maxsplit=1)[0].split("_", maxsplit=1)[0]
        aliases = {
            "evaluation_scoring": ModelPurpose.EVALUATION.value,
            "document_analysis": ModelPurpose.ANALYSIS.value,
            "knowledge_qa": ModelPurpose.ANALYSIS.value,
            "qna": ModelPurpose.ANALYSIS.value,
        }
        purpose = aliases.get(normalized, aliases.get(purpose, purpose))
        return list(dict.fromkeys([normalized, purpose]))

    @staticmethod
    def _default_rule(task_type: str) -> RoutingRule:
        """返回用途级代码兜底路由。"""
        purpose = ModelConfigManager._routing_candidates(task_type)[-1]
        defaults = {
            ModelPurpose.ANALYSIS.value: RoutingRule(
                type=ModelType.LLM,
                provider="deepseek",
                model=DefaultModel.ANALYSIS.value,
                fallbacks=[{"provider": "openai", "model": DefaultModel.EVALUATION.value}],
            ),
            ModelPurpose.PLANNING.value: RoutingRule(
                type=ModelType.LLM,
                provider="deepseek",
                model=DefaultModel.PLANNING.value,
                fallbacks=[{"provider": "openai", "model": DefaultModel.EVALUATION.value}],
            ),
            ModelPurpose.GENERATION.value: RoutingRule(
                type=ModelType.LLM,
                provider="deepseek",
                model=DefaultModel.GENERATION.value,
                fallbacks=[{"provider": "openai", "model": DefaultModel.EVALUATION.value}],
            ),
            ModelPurpose.EVALUATION.value: RoutingRule(
                type=ModelType.JUDGE,
                provider="openai",
                model=DefaultModel.EVALUATION.value,
                fallbacks=[{"type": ModelType.LLM.value, "provider": "deepseek", "model": DefaultModel.DEFAULT.value}],
            ),
            ModelPurpose.VISION.value: RoutingRule(
                type=ModelType.VISION,
                provider="openai",
                model=DefaultModel.VISION.value,
            ),
        }
        return defaults.get(
            purpose,
            RoutingRule(
                type=ModelType.LLM,
                provider="deepseek",
                model=DefaultModel.DEFAULT.value,
                fallbacks=[{"provider": "openai", "model": DefaultModel.EVALUATION.value}],
            ),
        )

    def resolve_model(self, task_type: str) -> tuple[ModelConfig, str]:
        """根据 task_type 解析出完整的 ModelConfig 和模型名。

        Args:
            task_type: 任务类型。

        Returns:
            (ModelConfig, model_name) 元组。
        """
        rule = self.resolve_rule(task_type)

        model_type = rule.type
        provider = rule.provider
        model_name = rule.model or ""

        config = self.get_config(model_type, provider)

        # 如果路由规则指定了模型名，覆盖默认模型
        if model_name:
            config.default_model = model_name

        return config, config.default_model

    def resolve_rule(
        self,
        task_type: str,
        provider: str = "",
        model: str = "",
    ) -> RoutingRule:
        """解析完整路由，并应用单次请求的 Provider/模型覆盖。"""
        rule = self.get_routing_rule(task_type) or self._default_rule(task_type)
        fallback = self._default_rule(task_type)
        data = rule.model_dump()
        # 环境变量只表达主路由，不应意外擦除 YAML/代码层的容灾链和超时。
        # 运行时配置若显式提供 fallbacks=[]，仍保留其“禁用回退”语义。
        is_runtime_rule = any(candidate in self._runtime_routing for candidate in self._routing_candidates(task_type))
        if not data["fallbacks"] and not is_runtime_rule:
            data["fallbacks"] = fallback.fallbacks
        if data["timeout"] is None:
            data["timeout"] = fallback.timeout
        if provider:
            data["provider"] = provider
        if model:
            data["model"] = model
        resolved = RoutingRule(**data)
        if not resolved.provider or not resolved.model:
            resolved.provider = resolved.provider or fallback.provider
            resolved.model = resolved.model or fallback.model
        return resolved

    def reset_to_env(self) -> None:
        """清除运行时配置，恢复到环境变量配置。"""
        self._runtime_config.clear()
        self._runtime_routing.clear()
