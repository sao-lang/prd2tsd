"""Contracts — 跨 Layer 接口定义和数据模型。"""

from contracts.interfaces import (
    AnalysisResult,
    Component,
    Constraint,
    EvaluationReport,
    GenerationResult,
    PlanningResult,
    Requirement,
    RetrievalContext,
    ScoredDoc,
    TechChoice,
)
from contracts.models import (
    FullModelConfig,
    ModelConfig,
    ModelConfigUpdate,
    ModelEndpointConfig,
    ModelType,
    ProviderType,
    RoutingRule,
    RoutingRuleUpdate,
)

__all__ = [
    # interfaces
    "RetrievalContext",
    "ScoredDoc",
    "AnalysisResult",
    "Requirement",
    "Constraint",
    "PlanningResult",
    "TechChoice",
    "Component",
    "GenerationResult",
    "EvaluationReport",
    # models
    "ModelType",
    "ProviderType",
    "ModelConfig",
    "ModelEndpointConfig",
    "RoutingRule",
    "FullModelConfig",
    "ModelConfigUpdate",
    "RoutingRuleUpdate",
]
