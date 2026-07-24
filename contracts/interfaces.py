"""所有 Layer 的接口定义（块 A 定义后不允许修改）。

Block C 新增：
- RequirementDetail / ConstraintDetail / AnalysisResultDetail（增强版分析模型）
- PatternEval / PlanningResultDetail（规划层模型）
- SectionOutline / GenerationResultDetail（生成层模型）
- EvaluationReportDetail（评测层模型）
- DocumentSection / DependencyGraph（辅助模型）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

# ════════════════════════════════════════════
# 原有 @dataclass 模型（块 A 定义，保持兼容）
# ════════════════════════════════════════════

# ── 知识检索 ──


@dataclass
class ScoredDoc:
    """带分数的检索文档。"""

    doc_id: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalContext:
    """知识检索结果。"""

    query: str
    docs: list[ScoredDoc]
    search_mode: str


# ── 分析层（基础）──


@dataclass
class Requirement:
    """需求项。"""

    id: str
    title: str
    description: str
    priority: str = "medium"
    category: str = "functional"


@dataclass
class Constraint:
    """约束条件。"""

    id: str
    description: str
    type: str = "technical"  # technical / business / regulatory


@dataclass
class AnalysisResult:
    """分析层输出。"""

    project_name: str
    summary: str
    requirements: list[Requirement]
    constraints: list[Constraint]
    metadata: dict[str, Any] = field(default_factory=dict)


# ── 规划层（基础）──


@dataclass
class TechChoice:
    """技术选型项。"""

    component: str
    technology: str
    version: str = ""
    reason: str = ""


@dataclass
class Component:
    """系统组件。"""

    name: str
    description: str
    tech_stack: list[TechChoice] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class PlanningResult:
    """规划层输出。"""

    architecture_pattern: str
    tech_stack: list[TechChoice]
    components: list[Component]
    metadata: dict[str, Any] = field(default_factory=dict)


# ── 生成层（基础）──


@dataclass
class GenerationResult:
    """生成层输出。"""

    content: str
    sections: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)


# ── 评测层（基础）──


@dataclass
class EvaluationReport:
    """评测报告。"""

    overall_score: float
    dimension_scores: dict[str, float]
    conclusion: str
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ════════════════════════════════════════════
# Block C — 增强 Pydantic 模型
# ════════════════════════════════════════════

# ── C1: 分析层增强 ──


class RequirementDetail(BaseModel):
    """增强需求项（C1）。"""

    id: str
    type: Literal["functional", "non_functional"]
    category: str
    priority: Literal["P0", "P1", "P2", "P3"]
    description: str
    actor: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    source_section: str = ""


class ConstraintDetail(BaseModel):
    """增强约束项（C1）。"""

    type: Literal["technical", "performance", "time", "budget", "compliance", "team"]
    description: str
    severity: Literal["must", "should", "could"]
    source_section: str = ""


class DocumentSection(BaseModel):
    """文档章节（C1 解析结果）。"""

    title: str
    level: int
    content: str
    subsections: list[DocumentSection] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    """需求依赖关系图（C1）。"""

    nodes: list[str] = Field(default_factory=list)
    edges: list[tuple[str, str, str]] = Field(default_factory=list)  # (from_id, to_id, relation)


class AnalysisResultDetail(BaseModel):
    """增强分析结果（C1 输出）。"""

    project_name: str
    summary: str
    domain_tags: list[str] = Field(default_factory=list)
    requirements: list[RequirementDetail] = Field(default_factory=list)
    constraints: list[ConstraintDetail] = Field(default_factory=list)
    dependency_graph: DependencyGraph = Field(default_factory=DependencyGraph)
    confidence: float = 0.0


# ── C2: 规划层增强 ──


class PatternEval(BaseModel):
    """架构模式评估（C2）。"""

    pattern_name: str
    match_score: float
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    complexity: Literal["low", "medium", "high"] = "medium"


class TechChoiceDetail(BaseModel):
    """增强技术选型项（C2）。"""

    dimension: str
    recommendation: str
    reason: str = ""
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ComponentDetail(BaseModel):
    """增强组件定义（C2）。"""

    name: str
    type: Literal["service", "module", "library"] = "service"
    responsibility: str = ""
    key_functions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class PlanningResultDetail(BaseModel):
    """增强规划结果（C2 输出）。"""

    architecture_pattern: str = ""
    tech_stack: list[TechChoiceDetail] = Field(default_factory=list)
    components: list[ComponentDetail] = Field(default_factory=list)
    component_diagram: str = ""


# ── C3: 生成层增强 ──


class SectionOutline(BaseModel):
    """章节大纲（C3）。"""

    section_id: str
    title: str
    level: int = 1
    description: str = ""
    estimated_tokens: int = 0


class GenerationResultDetail(BaseModel):
    """增强生成结果（C3 输出）。"""

    content: str = ""
    sections: dict[str, str] = Field(default_factory=dict)
    mermaid_diagrams: dict[str, str] = Field(default_factory=dict)


# ── C4: 评测层增强 ──


class EvaluationReportDetail(BaseModel):
    """增强评测报告（C4 输出）。"""

    overall_score: float = 0.0
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    conclusion: Literal["通过", "预警通过", "不通过"] = "不通过"
    p0_coverage: float = 0.0
    critical_issues: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
