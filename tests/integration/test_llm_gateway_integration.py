"""LLM Gateway 集成测试（使用模拟配置）。"""

from __future__ import annotations

import pytest

from app.llm_gateway.config_manager import ModelConfigManager


@pytest.mark.asyncio
async def test_config_resolution():
    """验证模型配置解析正确。"""
    manager = ModelConfigManager()
    config, model = manager.resolve_model("analysis.requirement")
    assert config is not None
    assert model is not None


@pytest.mark.asyncio
async def test_cost_tracking():
    """验证成本可追踪。"""
    from app.llm_gateway.cost_tracker import CostTracker

    tracker = CostTracker()
    tracker.record("deepseek-chat", input_tokens=100, output_tokens=50)
    assert tracker.get_total_cost() > 0
    assert tracker.get_total_tokens() == 150
