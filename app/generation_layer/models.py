"""C3 — Generation Layer 状态与结果模型。"""

from __future__ import annotations

from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    GenerationResultDetail,
    PlanningResultDetail,
    SectionOutline,
)


class GenerationState(TypedDict):
    """生成层状态（LangGraph State）。"""

    planning_result: PlanningResultDetail
    analysis_result: AnalysisResultDetail
    outline: list[SectionOutline]
    section_contents: dict[str, str]
    generation_result: GenerationResultDetail
