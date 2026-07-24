"""C4 — Evaluation Layer 状态与结果模型。"""

from __future__ import annotations

from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    EvaluationReportDetail,
    GenerationResultDetail,
    PlanningResultDetail,
)


class EvaluationState(TypedDict):
    """评测层状态（LangGraph State）。"""

    analysis_result: AnalysisResultDetail
    planning_result: PlanningResultDetail
    generation_result: GenerationResultDetail
    evaluation_report: EvaluationReportDetail
    dimension_scores: dict[str, float]  # 各节点写入维度评分，ScoringNode 汇总
