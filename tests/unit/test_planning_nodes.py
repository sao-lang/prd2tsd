"""C2 Planning Layer — 节点单元测试。"""

from __future__ import annotations

from contracts.interfaces import AnalysisResultDetail, PatternEval, PlanningResultDetail, ComponentDetail
from app.planning_layer.models import PlanningState
from app.planning_layer.nodes.pattern_confirm import PatternConfirmNode
from app.planning_layer.nodes.plan_assembler import PlanAssemblerNode


def _empty_pr() -> PlanningResultDetail:
    return PlanningResultDetail()


def test_pattern_confirm_selects_best():
    """验证 PatternConfirmNode 选择最高分模式。"""
    node = PatternConfirmNode()
    state: PlanningState = {
        "analysis_result": AnalysisResultDetail(project_name="Test", summary=""),
        "knowledge_context": None,
        "architecture_patterns": [
            PatternEval(pattern_name="微服务", match_score=9.0, complexity="high"),
            PatternEval(pattern_name="单体", match_score=5.0, complexity="low"),
        ],
        "selected_pattern": "",
        "tech_stack_choices": [],
        "component_decomposition": [],
        "planning_result": _empty_pr(),
    }
    result = node.run(state)
    assert result["selected_pattern"] == "微服务"


def test_assembler_generates_mermaid():
    """验证 PlanAssemblerNode 生成 Mermaid 图。"""
    node = PlanAssemblerNode()
    state: PlanningState = {
        "analysis_result": AnalysisResultDetail(project_name="Test", summary=""),
        "knowledge_context": None,
        "architecture_patterns": [],
        "selected_pattern": "微服务",
        "tech_stack_choices": [],
        "component_decomposition": [
            ComponentDetail(name="用户服务", type="service", responsibility="用户管理"),
            ComponentDetail(name="订单服务", type="service", responsibility="订单处理", dependencies=["用户服务"]),
        ],
        "planning_result": _empty_pr(),
    }
    result = node.run(state)
    assert "graph TD" in result["planning_result"].component_diagram
    assert "用户服务" in result["planning_result"].component_diagram
