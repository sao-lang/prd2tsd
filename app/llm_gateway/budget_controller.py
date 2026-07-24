"""预算控制器 — 工作空间月预算管理与自动降级。"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("prd2tsd.budget")


class BudgetController:
    """预算控制器。

    管理每个工作空间的月预算：
    - 查询当前月累计成本
    - 检查预算阈值（超过 90% 告警/自动降级）
    - 获取工作空间预算配置
    """

    def __init__(self) -> None:
        """初始化预算控制器。"""
        self._monthly_costs: dict[str, float] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    async def get_monthly_cost(self, workspace_id: str) -> float:
        """获取工作空间本月累计成本。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            本月累计成本（美元）。
        """
        return self._monthly_costs.get(workspace_id, 0.0)

    async def get_budget_config(self, workspace_id: str) -> dict[str, Any]:
        """获取工作空间预算配置。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            预算配置字典。
        """
        config = self._configs.get(workspace_id)
        if config is None:
            config = {
                "monthly_budget_usd": float(settings.BUDGET_DEFAULT_MONTHLY_USD),
                "alert_threshold": float(settings.BUDGET_DEFAULT_ALERT_THRESHOLD),
                "auto_downgrade": bool(settings.BUDGET_DEFAULT_AUTO_DOWNGRADE),
            }
        return config

    async def check_and_record(
        self,
        workspace_id: str,
        cost: float,
        model: str = "",
    ) -> dict[str, Any]:
        """检查预算并记录本次成本。

        检查流程：
        1. 获取工作空间预算配置
        2. 计算当前月累计成本
        3. 判断是否触发告警阈值
        4. 如需自动降级则返回降级信号

        Args:
            workspace_id: 工作空间 ID。
            cost: 本次调用成本。
            model: 本次使用的模型名。

        Returns:
            包含预算检查结果的字典：{
                "within_budget": bool,
                "usage_ratio": float,
                "should_downgrade": bool,
                "alert": bool,
            }
        """
        current_total = self._monthly_costs.get(workspace_id, 0.0) + cost
        self._monthly_costs[workspace_id] = current_total

        config = await self.get_budget_config(workspace_id)
        monthly_budget = float(config["monthly_budget_usd"])
        alert_threshold = float(config["alert_threshold"])

        usage_ratio = current_total / monthly_budget if monthly_budget > 0 else 0.0

        result: dict[str, Any] = {
            "within_budget": usage_ratio < 1.0,
            "usage_ratio": round(usage_ratio, 4),
            "should_downgrade": False,
            "alert": False,
        }

        if usage_ratio >= 1.0:
            logger.warning(
                "工作空间 %s 预算已超限: %.2f / %.2f",
                workspace_id, current_total, monthly_budget,
            )
            result["within_budget"] = False
            if config.get("auto_downgrade", True):
                result["should_downgrade"] = True
        elif usage_ratio >= alert_threshold:
            logger.warning(
                "工作空间 %s 预算使用 %.1f%%（阈值 %.0f%%）",
                workspace_id, usage_ratio * 100, alert_threshold * 100,
            )
            result["alert"] = True
            if config.get("auto_downgrade", True):
                result["should_downgrade"] = True

        return result

    async def set_budget_config(
        self,
        workspace_id: str,
        monthly_budget_usd: float | None = None,
        alert_threshold: float | None = None,
        auto_downgrade: bool | None = None,
    ) -> dict[str, Any]:
        """设置工作空间预算配置。

        Args:
            workspace_id: 工作空间 ID。
            monthly_budget_usd: 月预算（美元）。
            alert_threshold: 告警阈值（0-1）。
            auto_downgrade: 是否自动降级。

        Returns:
            更新后的预算配置。
        """
        config = await self.get_budget_config(workspace_id)
        if monthly_budget_usd is not None:
            config["monthly_budget_usd"] = monthly_budget_usd
        if alert_threshold is not None:
            config["alert_threshold"] = alert_threshold
        if auto_downgrade is not None:
            config["auto_downgrade"] = auto_downgrade
        self._configs[workspace_id] = config
        logger.info("工作空间 %s 预算配置已更新", workspace_id)
        return config

    async def get_monthly_report(self, workspace_id: str) -> dict[str, Any]:
        """获取工作空间月度成本报告。

        Args:
            workspace_id: 工作空间 ID。

        Returns:
            成本报告字典。
        """
        config = await self.get_budget_config(workspace_id)
        monthly_cost = await self.get_monthly_cost(workspace_id)
        monthly_budget = float(config["monthly_budget_usd"])

        return {
            "workspace_id": workspace_id,
            "monthly_cost_usd": round(monthly_cost, 4),
            "monthly_budget_usd": monthly_budget,
            "usage_ratio": round(
                monthly_cost / monthly_budget if monthly_budget > 0 else 0.0, 4,
            ),
            "remaining_budget": round(monthly_budget - monthly_cost, 4),
            "alert_threshold": config["alert_threshold"],
            "auto_downgrade": config["auto_downgrade"],
        }


# 全局单例
budget_controller = BudgetController()
