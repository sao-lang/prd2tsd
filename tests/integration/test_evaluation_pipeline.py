"""C4 — Evaluation Layer 集成测试。"""

from __future__ import annotations

import pytest

from contracts.interfaces import AnalysisResultDetail, EvaluationReportDetail, GenerationResultDetail, PlanningResultDetail
from app.evaluation.agent_graph import evaluation_graph


@pytest.mark.asyncio
async def test_evaluation_initial_state():
    """验证 Evaluation Layer 能处理初始输入。"""
    mock_analysis = AnalysisResultDetail(project_name="电商平台", summary="")
    mock_planning = PlanningResultDetail(architecture_pattern="微服务")
    mock_generation = GenerationResultDetail(content="# 技术方案文档\n\n内容...")

    result = await evaluation_graph.ainvoke({
        "analysis_result": mock_analysis,
        "planning_result": mock_planning,
        "generation_result": mock_generation,
        "evaluation_report": EvaluationReportDetail(),
        "dimension_scores": {},
    })
    assert "evaluation_report" in result
