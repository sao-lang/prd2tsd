"""C4 — Evaluation Layer LangGraph StateGraph。"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.evaluation.models import EvaluationState
from app.evaluation.nodes import (
    ArchitectureQualityNode,
    ConsistencyEvalNode,
    CostEvalNode,
    FeasibilityEvalNode,
    ImplementabilityEvalNode,
    LegalComplianceEvalNode,
    PRDCoverageCheckNode,
    SecurityComplianceNode,
    TechAdvancementEvalNode,
)
from app.evaluation.scoring import ScoringNode

coverage_node = PRDCoverageCheckNode()
consistency_node = ConsistencyEvalNode()
feasibility_node = FeasibilityEvalNode()
arch_quality_node = ArchitectureQualityNode()
security_node = SecurityComplianceNode()
cost_eval_node = CostEvalNode()
impl_eval_node = ImplementabilityEvalNode()
tech_adv_node = TechAdvancementEvalNode()
legal_node = LegalComplianceEvalNode()
scoring_node = ScoringNode()


def build_evaluation_graph() -> StateGraph:
    """构建并编译 Evaluation Layer StateGraph。

    C4 链路：
    Coverage → Consistency → Feasibility → ArchitectureQuality
    → Security → CostEval → Implementability → TechAdvancement
    → Legal → Scoring

    Returns:
        编译后的 StateGraph。
    """
    graph = StateGraph(EvaluationState)

    graph.add_node("coverage", coverage_node.run)
    graph.add_node("consistency", consistency_node.run)
    graph.add_node("feasibility", feasibility_node.run)
    graph.add_node("arch_quality", arch_quality_node.run)
    graph.add_node("security", security_node.run)
    graph.add_node("cost_eval", cost_eval_node.run)
    graph.add_node("implementability", impl_eval_node.run)
    graph.add_node("tech_advancement", tech_adv_node.run)
    graph.add_node("legal", legal_node.run)
    graph.add_node("scoring", scoring_node.run)

    graph.set_entry_point("coverage")
    graph.add_edge("coverage", "consistency")
    graph.add_edge("consistency", "feasibility")
    graph.add_edge("feasibility", "arch_quality")
    graph.add_edge("arch_quality", "security")
    graph.add_edge("security", "cost_eval")
    graph.add_edge("cost_eval", "implementability")
    graph.add_edge("implementability", "tech_advancement")
    graph.add_edge("tech_advancement", "legal")
    graph.add_edge("legal", "scoring")
    graph.add_edge("scoring", END)

    return graph


evaluation_graph = build_evaluation_graph().compile()
