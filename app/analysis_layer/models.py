"""C1 — Analysis Layer 状态与结果模型。"""

from __future__ import annotations

from typing import Any

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
    stakeholders: list[dict[str, Any]]  # StakeholderAnalyzerNode 写入
    clarity_issues: list[str]  # ClarityCheckerNode 写入
    # 以下字段由 Orchestrator Adapter 注入
    knowledge_context: Any  # knowledge_layer.models.RetrievalContext | None
    system_prompt: str  # 租户自定义 System Prompt
