"""C4 — Evaluation Layer 状态与结果模型。"""

from __future__ import annotations

from typing import Annotated

from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    EvaluationReportDetail,
    GenerationResultDetail,
    PlanningResultDetail,
)


def merge_scores(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    """LangGraph reducer: 合并两个维度评分 dict。"""
    merged = dict(a)
    merged.update(b)
    return merged


class EvaluationState(TypedDict):
    """评测层状态（LangGraph State）。"""

    analysis_result: AnalysisResultDetail
    planning_result: PlanningResultDetail
    generation_result: GenerationResultDetail
    evaluation_report: EvaluationReportDetail
    dimension_scores: Annotated[dict[str, float], merge_scores]  # reducer 自动合并各节点写入的评分
