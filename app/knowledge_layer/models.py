"""知识层数据模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ── 实体类型常量 ──

EntityType = Literal[
    "TechStack",
    "Component",
    "ArchitecturePattern",
    "Constraint",
    "Concept",
]

VALID_ENTITY_TYPES: list[str] = [
    "TechStack",
    "Component",
    "ArchitecturePattern",
    "Constraint",
    "Concept",
]

# ── Claims 类型常量 ──

ClaimType = Literal[
    "comparison",
    "decision",
    "specification",
    "constraint",
    "prediction",
]

VALID_CLAIM_TYPES: list[str] = [
    "comparison",
    "decision",
    "specification",
    "constraint",
    "prediction",
]

# ── 实体融合动作 ──

ResolutionAction = Literal["merge", "new", "referred"]


class KGEntity(BaseModel):
    """知识图谱实体。"""

    id: str = ""
    name: str
    type: EntityType = "Concept"
    category: str = ""
    description: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] = Field(default_factory=list)
    confidence: float = 0.9
    source_text_unit_id: str = ""
    workspace_id: str = ""


class Claim(BaseModel):
    """声明性断言（Claims / Covariates）。

    从 Chunk 中提取的对比/决策/规格/约束/预测类断言。
    """

    id: str = ""
    subject: str
    subject_entity_id: str = ""
    object: str = ""
    object_entity_id: str = ""
    claim_type: ClaimType = "specification"
    content: str
    confidence: float = 0.9
    source_text_unit_id: str = ""
    workspace_id: str = ""


class ScoredDoc(BaseModel):
    """检索结果。"""

    id: str
    text: str
    score: float
    source: str = "hybrid"  # local / global / hybrid
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalContext(BaseModel):
    """检索上下文 — Pipeline 的最终输出。"""

    query: str
    mode: str = "hybrid"
    results: list[ScoredDoc] = Field(default_factory=list)
    matched_entities: list[KGEntity] = Field(default_factory=list)
    text_unit_evidence: list[str] = Field(default_factory=list)
    # Global Search 宏观总结（社区检测已简化，字段由 community_summary 更名）
    global_summary: str = ""
    total_tokens: int = 0


class BuildStats(BaseModel):
    """知识图谱构建统计。"""

    entities: int = 0
    relations: int = 0
    chunks: int = 0
    claims: int = 0
    file_path: str = ""
    workspace_id: str = ""


class Chunk(BaseModel):
    """文档分块结果。"""

    id: str = ""
    text: str
    level: Literal["sentence", "paragraph", "section"] = "paragraph"
    section_path: str = ""
    index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
