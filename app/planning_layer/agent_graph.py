"""C2 — Planning Layer LangGraph StateGraph。"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.planning_layer.models import PlanningState
from app.planning_layer.nodes import (
    APIPlanningNode,
    ComponentDecomposeNode,
    CostEstimatorNode,
    DataArchDesignNode,
    DeploymentPlanningNode,
    KnowledgeAugmentNode,
    PatternConfirmNode,
    PatternRecommendNode,
    PlanAssemblerNode,
    PlanSelfCheckNode,
    RiskQuantifierNode,
    SkillGapAnalyzerNode,
    TechStackSelectNode,
    TimelinePlannerNode,
)

# 实例化 Node
knowledge_augment = KnowledgeAugmentNode()
pattern_recommend = PatternRecommendNode()
pattern_confirm = PatternConfirmNode()
tech_stack_select = TechStackSelectNode()
component_decompose = ComponentDecomposeNode()
cost_estimator = CostEstimatorNode()
timeline_planner = TimelinePlannerNode()
skill_gap_analyzer = SkillGapAnalyzerNode()
risk_quantifier = RiskQuantifierNode()
data_arch_design = DataArchDesignNode()
api_planning = APIPlanningNode()
deployment_planning = DeploymentPlanningNode()
plan_self_check = PlanSelfCheckNode()
plan_assembler = PlanAssemblerNode()


def build_planning_graph() -> StateGraph:
    """构建并编译 Planning Layer StateGraph。

    C2 链路：
    KnowledgeAugment → PatternRecommend → PatternConfirm → TechStackSelect
    → ComponentDecompose → CostEstimator → TimelinePlanner → SkillGapAnalyzer
    → RiskQuantifier → DataArchDesign → APIPlanning → DeploymentPlanning
    → PlanSelfCheck → PlanAssembler

    Returns:
        编译后的 StateGraph。
    """
    graph = StateGraph(PlanningState)

    graph.add_node("knowledge_augment", knowledge_augment.run)
    graph.add_node("pattern_recommend", pattern_recommend.run)
    graph.add_node("pattern_confirm", pattern_confirm.run)
    graph.add_node("tech_stack_select", tech_stack_select.run)
    graph.add_node("component_decompose", component_decompose.run)
    graph.add_node("cost_estimator", cost_estimator.run)
    graph.add_node("timeline_planner", timeline_planner.run)
    graph.add_node("skill_gap_analyzer", skill_gap_analyzer.run)
    graph.add_node("risk_quantifier", risk_quantifier.run)
    graph.add_node("data_arch_design", data_arch_design.run)
    graph.add_node("api_planning", api_planning.run)
    graph.add_node("deployment_planning", deployment_planning.run)
    graph.add_node("self_check", plan_self_check.run)
    graph.add_node("assemble", plan_assembler.run)

    graph.set_entry_point("knowledge_augment")
    graph.add_edge("knowledge_augment", "pattern_recommend")
    graph.add_edge("pattern_recommend", "pattern_confirm")
    graph.add_edge("pattern_confirm", "tech_stack_select")
    graph.add_edge("tech_stack_select", "component_decompose")
    graph.add_edge("component_decompose", "cost_estimator")
    graph.add_edge("cost_estimator", "timeline_planner")
    graph.add_edge("timeline_planner", "skill_gap_analyzer")
    graph.add_edge("skill_gap_analyzer", "risk_quantifier")
    graph.add_edge("risk_quantifier", "data_arch_design")
    graph.add_edge("data_arch_design", "api_planning")
    graph.add_edge("api_planning", "deployment_planning")
    graph.add_edge("deployment_planning", "self_check")
    graph.add_edge("self_check", "assemble")
    graph.add_edge("assemble", END)

    return graph


planning_graph = build_planning_graph().compile()
