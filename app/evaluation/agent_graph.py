"""C4 — Evaluation Layer LangGraph StateGraph。

使用 Send() 实现 9 个评测维度并行执行，reducer 自动合并评分。
"""

from __future__ import annotations

from langgraph.constants import Send
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

# ── 评测维度 → dimension_scores 键名映射 ──
_EVALUATOR_DIMS: dict[str, str] = {
    "coverage": "prd_coverage",
    "consistency": "consistency",
    "feasibility": "feasibility",
    "arch_quality": "architecture_quality",
    "security": "security",
    "cost_eval": "cost",
    "implementability": "implementability",
    "tech_advancement": "tech_advancement",
    "legal": "legal_compliance",
}


def fan_out_evaluators(state: EvaluationState) -> list[Send]:
    """扇出：为每个未评估的维度创建一个 Send，允许并行 LLM 调用。

    利用 merge_scores reducer 自动合并各维度评分到 dimension_scores。

    Args:
        state: 当前状态。

    Returns:
        Send 列表（每个指向一个 evaluator 节点）。
    """
    existing = state.get("dimension_scores", {})
    sends: list[Send] = []
    for node_name, dim_key in _EVALUATOR_DIMS.items():
        if dim_key not in existing:
            sends.append(Send(node_name, state))

    # 所有维度已评估 → 直接路由到 scoring
    if not sends:
        sends.append(Send("scoring", state))
    return sends


def build_evaluation_graph() -> StateGraph:
    """构建并行评测 StateGraph。

    C4 链路：
    FanOut → [Coverage, Consistency, …, Legal 并行] → Scoring
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

    # 条件入口：Send() 扇出到所有 evaluator 节点并行执行
    graph.set_conditional_entry_point(
        fan_out_evaluators,
        list(_EVALUATOR_DIMS.keys()) + ["scoring"],
    )

    # Fan-in：所有 evaluator 完成后才进入 scoring
    for node_name in _EVALUATOR_DIMS:
        graph.add_edge(node_name, "scoring")
    graph.add_edge("scoring", END)

    return graph


evaluation_graph = build_evaluation_graph().compile()
