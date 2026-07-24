"""C3 Generation Layer — 节点单元测试。"""

from __future__ import annotations

from contracts.interfaces import AnalysisResultDetail, GenerationResultDetail, PlanningResultDetail, SectionOutline
from app.generation_layer.models import GenerationState
from app.generation_layer.nodes.outline_node import OutlineGeneratorNode
from app.generation_layer.nodes.format_assembler import FormatAssemblerNode


def _empty_gr() -> GenerationResultDetail:
    return GenerationResultDetail()


def test_outline_generates_sections():
    """验证 OutlineGeneratorNode 生成大纲。"""
    node = OutlineGeneratorNode()
    state: GenerationState = {
        "planning_result": PlanningResultDetail(architecture_pattern="微服务"),
        "analysis_result": AnalysisResultDetail(project_name="电商平台", summary="", domain_tags=["电商"]),
        "outline": [],
        "section_contents": {},
        "generation_result": _empty_gr(),
    }
    result = node.run(state)
    assert len(result["outline"]) >= 1


def test_assembler_creates_markdown():
    """验证 FormatAssemblerNode 组装 Markdown。"""
    node = FormatAssemblerNode()
    state: GenerationState = {
        "planning_result": PlanningResultDetail(),
        "analysis_result": AnalysisResultDetail(project_name="Test", summary=""),
        "outline": [
            SectionOutline(section_id="intro", title="简介", level=1, description="", estimated_tokens=100),
        ],
        "section_contents": {"intro": "# 简介\n\n这是简介内容。"},
        "generation_result": _empty_gr(),
    }
    result = node.run(state)
    assert "简介" in result["generation_result"].content
    assert result["generation_result"].sections["intro"] == "# 简介\n\n这是简介内容。"
