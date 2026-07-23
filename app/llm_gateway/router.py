"""模型路由器 — 根据 task_type 选择模型。"""

from __future__ import annotations

from app.llm_gateway.config_manager import ModelConfigManager
from contracts.models import ModelConfig, RoutingRule


class ModelRouter:
    """模型路由器。

    根据 task_type 从 ModelConfigManager 获取对应的模型配置和路由规则。
    """

    def __init__(self, config_manager: ModelConfigManager) -> None:
        """初始化模型路由器。

        Args:
            config_manager: 模型配置管理器实例。
        """
        self.config_manager = config_manager

    def resolve(self, task_type: str) -> tuple[ModelConfig, str]:
        """根据 task_type 解析模型配置。

        Args:
            task_type: 任务类型，例如 "analysis.requirement"、"evaluation.scoring"。

        Returns:
            (ModelConfig, model_name) 元组。
        """
        return self.config_manager.resolve_model(task_type)

    def get_rule(self, task_type: str) -> RoutingRule | None:
        """获取指定任务类型的路由规则。

        Args:
            task_type: 任务类型。

        Returns:
            路由规则，不存在时返回 None。
        """
        return self.config_manager.get_routing_rule(task_type)

    def update_rule(self, task_type: str, rule: RoutingRule) -> None:
        """更新指定任务类型的路由规则。

        Args:
            task_type: 任务类型。
            rule: 新的路由规则。
        """
        self.config_manager.update_routing_rule(task_type, rule)

    def list_rules(self) -> dict[str, RoutingRule]:
        """列出所有可用的路由规则。

        Returns:
            {task_type: RoutingRule} 字典。
        """
        rules: dict[str, RoutingRule] = {}
        # 从环境变量中读取已定义的路由规则
        task_types = [
            "analysis.requirement",
            "analysis.constraint",
            "planning.architecture",
            "evaluation.scoring",
            "embedding",
            "rerank",
        ]
        for tt in task_types:
            rule = self.get_rule(tt)
            if rule:
                rules[tt] = rule
        return rules
