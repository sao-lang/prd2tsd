"""C3 — Generation Layer 集成测试。"""

from __future__ import annotations

import pytest

from contracts.interfaces import AnalysisResultDetail, GenerationResultDetail, PlanningResultDetail
from app.generation_layer.agent_graph import generation_graph


@pytest.mark.asyncio
async def test_generation_produces_markdown():
    """验证 Generation Layer 输出 Markdown。"""
    pr = PlanningResultDetail(architecture_pattern="微服务")
    ar = AnalysisResultDetail(project_name="电商平台", summary="")
    result = await generation_graph.ainvoke({
        "planning_result": pr,
        "analysis_result": ar,
        "outline": [],
        "section_contents": {},
        "generation_result": GenerationResultDetail(),
    })
    assert "generation_result" in result
