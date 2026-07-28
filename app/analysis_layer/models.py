"""C1 — Analysis Layer 状态与结果模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    ConstraintDetail,
    DependencyGraph,
    DocumentSection,
    RequirementDetail,
)

# ── Phase 6: LangChain 结构化输出模型 ──


class RequirementList(BaseModel):
    """需求列表 — LLM 结构化输出。"""

    requirements: list[RequirementDetail] = Field(default_factory=list)


class StakeholderList(BaseModel):
    """干系人列表 — LLM 结构化输出。"""

    stakeholders: list[dict[str, Any]] = Field(default_factory=list)


class ConstraintList(BaseModel):
    """约束列表 — LLM 结构化输出。"""

    constraints: list[ConstraintDetail] = Field(default_factory=list)


class DependencyResult(BaseModel):
    """依赖关系结果 — LLM 结构化输出。"""

    dependency_graph: DependencyGraph = Field(default_factory=DependencyGraph)


class DomainResult(BaseModel):
    """领域分类结果 — LLM 结构化输出。"""

    domain_tags: list[str] = Field(default_factory=list)
    primary_domain: str = ""


class EffortResult(BaseModel):
    """工作量评估结果 — LLM 结构化输出。"""

    total_effort_days: float = 0.0
    complexity: str = "medium"
    breakdown: dict[str, float] = Field(default_factory=dict)


class QualityResult(BaseModel):
    """需求质量评估 — LLM 结构化输出。"""

    score: float = 0.0
    clarity_score: float = 0.0
    completeness_score: float = 0.0
    consistency_score: float = 0.0
    issues: list[str] = Field(default_factory=list)


class LanguageResult(BaseModel):
    """语言检测结果 — LLM 结构化输出。"""

    language: str = "zh"
    confidence: float = 0.0


class ClarityResult(BaseModel):
    """清晰度检查结果 — LLM 结构化输出。"""

    passed: bool = True
    issues: list[str] = Field(default_factory=list)


# ── State ──


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
