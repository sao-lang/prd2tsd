"""FormatExporterNode — ⭐ 多格式导出单元测试。"""

from __future__ import annotations

from contracts.interfaces import AnalysisResultDetail, GenerationResultDetail, PlanningResultDetail
from app.generation_layer.models import GenerationState
from app.generation_layer.nodes.format_exporter import FormatExporterNode


def test_format_exporter_placeholder():
    """验证 FormatExporterNode 占位节点不报错。"""
    node = FormatExporterNode()
    state: GenerationState = {
        "planning_result": PlanningResultDetail(),
        "analysis_result": AnalysisResultDetail(project_name="Test", summary=""),
        "outline": [],
        "section_contents": {},
        "generation_result": GenerationResultDetail(content="# Test", sections={"test": "# Test"}),
    }
    result = node.run(state)
    assert result is not None
