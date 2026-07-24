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
