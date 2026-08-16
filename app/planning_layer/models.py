"""C2 — Planning Layer 状态与结果模型。"""

from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    ComponentDetail,
    PatternEval,
    PlanningResultDetail,
    TechChoiceDetail,
)


class PlanningState(TypedDict):
    """规划层状态（LangGraph State）。"""

    analysis_result: AnalysisResultDetail
    knowledge_context: Any  # knowledge_layer.models.RetrievalContext | None
    architecture_patterns: list[PatternEval]
    selected_pattern: str
    tech_stack_choices: list[TechChoiceDetail]
    component_decomposition: list[ComponentDetail]
    planning_result: PlanningResultDetail
    node_outputs: dict[str, Any]  # 各子节点的 LLM 输出缓存
    self_check_attempts: int  # 自检失败回退重规划的次数（防无限递归）
    # 以下字段由 Orchestrator Adapter 注入（迭代反馈）
    evaluation_feedback: dict[str, Any]  # {issues, recommendations, overall_score}
