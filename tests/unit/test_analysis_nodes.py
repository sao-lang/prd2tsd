"""C1 Analysis Layer — 节点单元测试。"""

from __future__ import annotations

from contracts.interfaces import AnalysisResultDetail, DependencyGraph, DocumentSection
from app.analysis_layer.models import AnalysisState
from app.analysis_layer.nodes.parse_node import DocumentParserNode
from app.analysis_layer.nodes.result_assembler import AnalysisResultAssemblerNode


def _empty_ar() -> AnalysisResultDetail:
    return AnalysisResultDetail(project_name="", summary="")


def _empty_dg() -> DependencyGraph:
    return DependencyGraph()


def test_parse_node_splits_sections():
    """验证 DocumentParserNode 能按标题拆分章节。"""
    node = DocumentParserNode()
    state: AnalysisState = {
        "prd_raw": "# 项目名称\n## 功能需求\n1. 用户登录\n## 非功能需求\n高性能",
        "prd_sections": [],
        "extracted_requirements": [],
        "extracted_constraints": [],
        "dependency_graph": _empty_dg(),
        "domain_tags": [],
        "analysis_result": _empty_ar(),
        "confidence": 0.0,
    }
    result = node.run(state)
    assert len(result["prd_sections"]) >= 2
    assert result["prd_sections"][0].title == "项目名称"


def test_assembler_creates_result():
    """验证 AnalysisResultAssemblerNode 能组装结果。"""
    node = AnalysisResultAssemblerNode()
    state: AnalysisState = {
        "prd_raw": "# 电商平台\n一个电商系统",
        "prd_sections": [DocumentSection(title="电商平台", level=1, content="一个电商系统")],
        "extracted_requirements": [],
        "extracted_constraints": [],
        "dependency_graph": _empty_dg(),
        "domain_tags": ["电商"],
        "analysis_result": _empty_ar(),
        "confidence": 0.8,
    }
    result = node.run(state)
    assert result["analysis_result"].project_name == "电商平台"
    assert "电商" in result["analysis_result"].domain_tags
