"""预算控制器单元测试。"""

from __future__ import annotations

import pytest

from app.llm_gateway.budget_controller import BudgetController


@pytest.fixture
def budget() -> BudgetController:
    """创建干净的预算控制器。"""
    return BudgetController()


@pytest.mark.asyncio
async def test_budget_within_limit(budget: BudgetController) -> None:
    """验证预算未超限时正常。"""
    result = await budget.check_and_record("ws-1", 1.0)
    assert result["within_budget"] is True
    assert result["should_downgrade"] is False


@pytest.mark.asyncio
async def test_budget_exceeds_limit(budget: BudgetController) -> None:
    """验证预算超限时触发降级。"""
    # 手动设置低预算
    await budget.set_budget_config("ws-2", monthly_budget_usd=5.0)
    # 使用 6 美元（超预算）
    result = await budget.check_and_record("ws-2", 6.0)
    assert result["within_budget"] is False
    assert result["should_downgrade"] is True


@pytest.mark.asyncio
async def test_budget_alert_threshold(budget: BudgetController) -> None:
    """验证预算超过 90% 阈值时告警。"""
    await budget.set_budget_config("ws-3", monthly_budget_usd=100.0, alert_threshold=0.9)
    # 使用 95 美元（超 90% 阈值）
    result = await budget.check_and_record("ws-3", 95.0)
    assert result["alert"] is True
    assert result["should_downgrade"] is True
    assert result["usage_ratio"] == 0.95


@pytest.mark.asyncio
async def test_budget_monthly_report(budget: BudgetController) -> None:
    """验证月度成本报告。"""
    await budget.set_budget_config("ws-4", monthly_budget_usd=200.0)
    await budget.check_and_record("ws-4", 50.0)
    report = await budget.get_monthly_report("ws-4")
    assert report["workspace_id"] == "ws-4"
    assert report["monthly_cost_usd"] == 50.0
    assert report["monthly_budget_usd"] == 200.0
    assert report["usage_ratio"] == 0.25
    assert report["remaining_budget"] == 150.0


@pytest.mark.asyncio
async def test_budget_default_config(budget: BudgetController) -> None:
    """验证默认预算配置。"""
    config = await budget.get_budget_config("ws-new")
    assert config["monthly_budget_usd"] > 0
    assert config["alert_threshold"] == 0.9
    assert config["auto_downgrade"] is True


@pytest.mark.asyncio
async def test_budget_cumulative_cost(budget: BudgetController) -> None:
    """验证同工作空间累积成本。"""
    await budget.check_and_record("ws-5", 10.0)
    await budget.check_and_record("ws-5", 20.0)
    monthly = await budget.get_monthly_cost("ws-5")
    assert monthly == 30.0
