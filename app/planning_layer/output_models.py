"""Planning Layer — LangChain 结构化输出模型。"""

from typing import Any

from pydantic import BaseModel, Field


class CostEstimateTier(BaseModel):
    """单层成本方案。"""

    monthly: float = Field(description="月成本（美元）")
    desc: str = Field(description="方案描述")
    risks: list[str] = Field(default_factory=list, description="风险列表")


class CostEstimateResult(BaseModel):
    """三层成本估算结果。"""

    low_cost: CostEstimateTier = Field(description="最低配置")
    standard: CostEstimateTier = Field(description="标准配置")
    high_availability: CostEstimateTier = Field(description="高可用配置")


class RiskItem(BaseModel):
    """单条风险项。"""

    risk: str = Field(description="风险名称")
    probability: float = Field(description="概率 (0-1)")
    impact: float = Field(description="影响 (0-1)")
    risk_score: float = Field(description="风险评分")
    mitigation: str = Field(description="缓解措施")


class RiskQuantifyResult(BaseModel):
    """风险量化结果。"""

    risks: list[RiskItem] = Field(default_factory=list, description="风险列表")


class DecomposedComponent(BaseModel):
    """组件分解结果。"""

    name: str = Field(description="组件名")
    type: str = Field(description="组件类型 (service/library/database 等)")
    responsibility: str = Field(description="组件职责描述")
    key_functions: list[str] = Field(default_factory=list, description="关键功能")
    dependencies: list[str] = Field(default_factory=list, description="依赖项")


class ComponentDecomposeResult(BaseModel):
    """组件分解结果列表。"""

    components: list[DecomposedComponent] = Field(default_factory=list)


class ArchitecturePattern(BaseModel):
    """架构模式评估。"""

    pattern_name: str = Field(description="模式名称")
    match_score: float = Field(description="匹配度 (0-10)")
    strengths: list[str] = Field(default_factory=list, description="优势")
    weaknesses: list[str] = Field(default_factory=list, description="劣势")
    complexity: str = Field(description="复杂度 (low/medium/high)")


class PatternRecommendResult(BaseModel):
    """架构模式推荐结果。"""

    patterns: list[ArchitecturePattern] = Field(default_factory=list)


class TechStackItem(BaseModel):
    """单维度技术栈选型。"""

    dimension: str = Field(description="维度 (backend_framework/database_primary 等)")
    recommendation: str = Field(description="推荐方案")
    reason: str = Field(description="推荐理由")
    alternatives: list[dict[str, Any]] = Field(default_factory=list, description="备选方案")
    risks: list[str] = Field(default_factory=list, description="风险")


class TechStackResult(BaseModel):
    """技术栈选型结果。"""

    choices: list[TechStackItem] = Field(default_factory=list)


class SelfCheckResult(BaseModel):
    """规划自检结果。"""

    passed: bool = Field(description="是否通过自检")
    score: float = Field(default=5.0, description="评分 (0-10)")
    issues: list[str] = Field(default_factory=list, description="发现的问题")
