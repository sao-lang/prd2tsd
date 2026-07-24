"""C1 — Analysis Layer 状态与结果模型。"""

from __future__ import annotations

from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    ConstraintDetail,
    DependencyGraph,
    DocumentSection,
    RequirementDetail,
)


class AnalysisState(TypedDict):
    """分析层状态（LangGraph State）。"""

    prd_raw: str
    prd_sections: list[DocumentSection]
    extracted_requirements: list[RequirementDetail]
    extracted_constraints: list[ConstraintDetail]
    dependency_graph: DependencyGraph
    domain_tags: list[str]
    analysis_result: AnalysisResultDetail
    confidence: float
