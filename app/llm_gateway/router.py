"""模型路由器（已废弃）— 功能已合并到 ModelConfigManager。

请直接使用 ModelConfigManager.resolve_model() / get_routing_rule() / update_routing_rule()。
"""

from __future__ import annotations

import warnings

from app.llm_gateway.config_manager import ModelConfigManager
from contracts.models import ModelConfig, RoutingRule

warnings.warn(
    "app.llm_gateway.router 已废弃，请使用 ModelConfigManager 的对应方法",
    DeprecationWarning,
    stacklevel=2,
)


class ModelRouter:
    """模型路由器（已废弃）。

    所有方法直接委托给 ModelConfigManager。请直接使用 ModelConfigManager。
    """

    def __init__(self, config_manager: ModelConfigManager) -> None:
        warnings.warn("ModelRouter 已废弃", DeprecationWarning, stacklevel=2)
        self.config_manager = config_manager

    def resolve(self, task_type: str) -> tuple[ModelConfig, str]:
        """（已废弃）根据 task_type 解析模型配置。请改用 ModelConfigManager.resolve_model。"""
        return self.config_manager.resolve_model(task_type)

    def get_rule(self, task_type: str) -> RoutingRule | None:
        """（已废弃）获取路由规则。请改用 ModelConfigManager.get_routing_rule。"""
        return self.config_manager.get_routing_rule(task_type)

    def update_rule(self, task_type: str, rule: RoutingRule) -> None:
        """（已废弃）更新路由规则。请改用 ModelConfigManager.update_routing_rule。"""
        self.config_manager.update_routing_rule(task_type, rule)

    def list_rules(self) -> dict[str, RoutingRule]:
        """（已废弃）列出路由规则。请改用 ModelConfigManager。"""
        return self.config_manager.list_rules() if hasattr(self.config_manager, "list_rules") else {}
