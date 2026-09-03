"""持久化工作空间预算控制器，支持周/月周期窗口。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.models.block_e import BudgetConfig, LLMCallLog

logger = get_logger("prd2tsd.budget")


class BudgetStore(Protocol):
    """预算持久化接口，便于数据库实现与单元测试隔离。"""

    async def get_config(self, workspace_id: str) -> dict[str, Any] | None:
        """读取工作空间预算配置。"""
        ...

    async def set_config(self, workspace_id: str, config: dict[str, Any]) -> None:
        """写入工作空间预算配置。"""
        ...

    async def get_cost(self, workspace_id: str, period_start: datetime) -> float:
        """汇总指定周期起点后的成本。"""
        ...

    async def record_cost(
        self,
        workspace_id: str,
        cost: float,
        model: str,
        input_tokens: int,
        output_tokens: int,
        layer: str,
        node: str,
    ) -> None:
        """追加一条实际成本记录。"""
        ...


class PostgresBudgetStore:
    """以 budget_configs 和 llm_call_logs 为持久化数据源。"""

    @staticmethod
    def _session() -> Any:
        connector = connection_manager.get("postgres")
        return connector.get_session()

    async def get_config(self, workspace_id: str) -> dict[str, Any] | None:
        """从 PostgreSQL 读取预算配置。"""
        async with self._session() as session:
            row = await session.scalar(select(BudgetConfig).where(BudgetConfig.workspace_id == workspace_id))
            if row is None:
                return None
            return {
                "monthly_budget_usd": float(row.monthly_budget_usd or 0),
                "weekly_budget_usd": float(row.weekly_budget_usd or 0),
                "budget_period": row.budget_period,
                "alert_threshold": float(row.alert_threshold),
                "auto_downgrade": row.auto_downgrade,
            }

    async def set_config(self, workspace_id: str, config: dict[str, Any]) -> None:
        """向 PostgreSQL 新增或更新预算配置。"""
        async with self._session() as session:
            row = await session.scalar(select(BudgetConfig).where(BudgetConfig.workspace_id == workspace_id))
            if row is None:
                row = BudgetConfig(workspace_id=workspace_id)
                session.add(row)
            row.monthly_budget_usd = config.get("monthly_budget_usd")
            row.weekly_budget_usd = config.get("weekly_budget_usd")
            row.budget_period = str(config.get("budget_period", "monthly"))
            row.alert_threshold = float(config.get("alert_threshold", 0.9))
            row.auto_downgrade = bool(config.get("auto_downgrade", True))
            await session.commit()

    async def get_cost(self, workspace_id: str, period_start: datetime) -> float:
        """从调用账本汇总当前周期成本。"""
        async with self._session() as session:
            total = await session.scalar(
                select(func.coalesce(func.sum(LLMCallLog.cost), 0)).where(
                    LLMCallLog.workspace_id == workspace_id,
                    LLMCallLog.created_at >= period_start,
                )
            )
            return float(total or 0)

    async def record_cost(
        self,
        workspace_id: str,
        cost: float,
        model: str,
        input_tokens: int,
        output_tokens: int,
        layer: str,
        node: str,
    ) -> None:
        """向 PostgreSQL 调用账本追加实际成本。"""
        if not workspace_id or cost <= 0:
            return
        async with self._session() as session:
            session.add(
                LLMCallLog(
                    workspace_id=workspace_id,
                    model=model or "unknown",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost=cost,
                    layer=layer or None,
                    node=node or None,
                    cached=False,
                )
            )
            await session.commit()


class MemoryBudgetStore:
    """仅供单元测试使用的确定性 BudgetStore。"""

    def __init__(self) -> None:
        self.configs: dict[str, dict[str, Any]] = {}
        self.costs: dict[str, list[tuple[datetime, float]]] = {}

    async def get_config(self, workspace_id: str) -> dict[str, Any] | None:
        """读取测试内存中的预算配置。"""
        return self.configs.get(workspace_id)

    async def set_config(self, workspace_id: str, config: dict[str, Any]) -> None:
        """写入测试内存中的预算配置。"""
        self.configs[workspace_id] = dict(config)

    async def get_cost(self, workspace_id: str, period_start: datetime) -> float:
        """汇总测试内存中的周期成本。"""
        return sum(cost for timestamp, cost in self.costs.get(workspace_id, []) if timestamp >= period_start)

    async def record_cost(
        self,
        workspace_id: str,
        cost: float,
        model: str,
        input_tokens: int,
        output_tokens: int,
        layer: str,
        node: str,
    ) -> None:
        """向测试内存账本追加实际成本。"""
        self.costs.setdefault(workspace_id, []).append((datetime.now(UTC), cost))


class BudgetController:
    """基于持久化账本执行预算检查、记录和周期报告。"""

    def __init__(self, store: BudgetStore | None = None) -> None:
        """初始化控制器；生产默认使用 PostgreSQL。"""
        self._store = store or PostgresBudgetStore()

    @staticmethod
    def _default_config() -> dict[str, Any]:
        return {
            "monthly_budget_usd": float(settings.BUDGET_DEFAULT_MONTHLY_USD),
            "weekly_budget_usd": 0.0,
            "budget_period": "monthly",
            "alert_threshold": float(settings.BUDGET_DEFAULT_ALERT_THRESHOLD),
            "auto_downgrade": bool(settings.BUDGET_DEFAULT_AUTO_DOWNGRADE),
        }

    @staticmethod
    def _period_start(period: str, now: datetime | None = None) -> datetime:
        current = now or datetime.now(UTC)
        if period == "weekly":
            start = current - timedelta(days=current.weekday())
            return start.replace(hour=0, minute=0, second=0, microsecond=0)
        return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def get_budget_config(self, workspace_id: str) -> dict[str, Any]:
        """读取工作空间持久化预算配置；数据库不可用时安全使用默认策略。"""
        if not workspace_id:
            return self._default_config()
        try:
            stored = await self._store.get_config(workspace_id)
        except (KeyError, RuntimeError, OSError, SQLAlchemyError) as exc:
            logger.error("预算配置存储不可用: workspace=%s error=%s", workspace_id, exc)
            stored = None
        return {**self._default_config(), **(stored or {})}

    async def get_period_cost(self, workspace_id: str, period: str) -> float:
        """读取当前周或月的累计成本。"""
        if not workspace_id:
            return 0.0
        try:
            return await self._store.get_cost(workspace_id, self._period_start(period))
        except (KeyError, RuntimeError, OSError, SQLAlchemyError) as exc:
            logger.error("预算账本不可用，按零用量降级: workspace=%s error=%s", workspace_id, exc)
            return 0.0

    async def get_monthly_cost(self, workspace_id: str) -> float:
        """兼容旧接口：获取当前自然月成本。"""
        return await self.get_period_cost(workspace_id, "monthly")

    async def check(self, workspace_id: str) -> dict[str, Any]:
        """只检查预算，不产生账本写入。"""
        config = await self.get_budget_config(workspace_id)
        period = str(config.get("budget_period", "monthly"))
        current_total = await self.get_period_cost(workspace_id, period)
        budget_key = "weekly_budget_usd" if period == "weekly" else "monthly_budget_usd"
        budget = float(config.get(budget_key) or settings.BUDGET_DEFAULT_MONTHLY_USD)
        threshold = float(config["alert_threshold"])
        usage_ratio = current_total / budget if budget > 0 else 0.0
        should_downgrade = bool(config.get("auto_downgrade", True)) and usage_ratio >= threshold
        return {
            "within_budget": usage_ratio < 1.0,
            "usage_ratio": round(usage_ratio, 4),
            "should_downgrade": should_downgrade,
            "alert": threshold <= usage_ratio < 1.0,
            "period": period,
            "period_start": self._period_start(period).isoformat(),
        }

    async def record_usage(
        self,
        workspace_id: str,
        cost: float,
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        layer: str = "",
        node: str = "",
    ) -> None:
        """将实际成本追加到持久化调用账本。"""
        if not workspace_id or cost <= 0:
            return
        try:
            await self._store.record_cost(
                workspace_id,
                cost,
                model,
                input_tokens,
                output_tokens,
                layer,
                node,
            )
        except (KeyError, RuntimeError, OSError, SQLAlchemyError) as exc:
            logger.error("预算成本未能持久化: workspace=%s model=%s error=%s", workspace_id, model, exc)

    async def check_and_record(self, workspace_id: str, cost: float, model: str = "") -> dict[str, Any]:
        """兼容旧接口：非零成本先落账，再返回最新预算状态。"""
        await self.record_usage(workspace_id, cost, model)
        return await self.check(workspace_id)

    async def set_budget_config(
        self,
        workspace_id: str,
        monthly_budget_usd: float | None = None,
        alert_threshold: float | None = None,
        auto_downgrade: bool | None = None,
        weekly_budget_usd: float | None = None,
        budget_period: str | None = None,
    ) -> dict[str, Any]:
        """持久化更新周/月预算配置。"""
        config = await self.get_budget_config(workspace_id)
        updates = {
            "monthly_budget_usd": monthly_budget_usd,
            "weekly_budget_usd": weekly_budget_usd,
            "alert_threshold": alert_threshold,
            "auto_downgrade": auto_downgrade,
            "budget_period": budget_period,
        }
        for key, value in updates.items():
            if value is not None:
                config[key] = value
        if config["budget_period"] not in {"weekly", "monthly"}:
            raise ValueError("budget_period 必须是 weekly 或 monthly")
        await self._store.set_config(workspace_id, config)
        return config

    async def get_monthly_report(self, workspace_id: str) -> dict[str, Any]:
        """兼容旧接口并返回当前配置周期报告。"""
        config = await self.get_budget_config(workspace_id)
        period = str(config["budget_period"])
        period_cost = await self.get_period_cost(workspace_id, period)
        budget_key = "weekly_budget_usd" if period == "weekly" else "monthly_budget_usd"
        budget = float(config.get(budget_key) or settings.BUDGET_DEFAULT_MONTHLY_USD)
        return {
            "workspace_id": workspace_id,
            "period": period,
            "period_start": self._period_start(period).isoformat(),
            "period_cost_usd": round(period_cost, 4),
            "monthly_cost_usd": round(await self.get_monthly_cost(workspace_id), 4),
            "monthly_budget_usd": float(config["monthly_budget_usd"]),
            "weekly_budget_usd": float(config["weekly_budget_usd"]),
            "usage_ratio": round(period_cost / budget if budget > 0 else 0.0, 4),
            "remaining_budget": round(budget - period_cost, 4),
            "alert_threshold": config["alert_threshold"],
            "auto_downgrade": config["auto_downgrade"],
        }


budget_controller = BudgetController()
