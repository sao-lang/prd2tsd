"""C2 — Planning Layer 集成测试。"""

from __future__ import annotations

import pytest

from contracts.interfaces import AnalysisResultDetail, PlanningResultDetail
from app.planning_layer.agent_graph import planning_graph


@pytest.mark.asyncio
async def test_planning_initial_state():
    """验证 Planning Layer 能处理初始输入。"""
    mock_analysis = AnalysisResultDetail(
        project_name="电商平台",
        summary="一个电商系统",
        domain_tags=["电商"],
    )
    result = await planning_graph.ainvoke({
        "analysis_result": mock_analysis,
        "knowledge_context": None,
        "architecture_patterns": [],
        "selected_pattern": "",
        "tech_stack_choices": [],
        "component_decomposition": [],
        "planning_result": PlanningResultDetail(),
    })
    assert "planning_result" in result
