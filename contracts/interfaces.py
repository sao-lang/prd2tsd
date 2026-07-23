"""所有 Layer 的接口定义（块 A 定义后不允许修改）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


# ── 分析层 ──


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


# ── 规划层 ──


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


# ── 生成层 ──


@dataclass
class GenerationResult:
    """生成层输出。"""

    content: str
    sections: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)


# ── 评测层 ──


@dataclass
class EvaluationReport:
    """评测报告。"""

    overall_score: float
    dimension_scores: dict[str, float]
    conclusion: str
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
