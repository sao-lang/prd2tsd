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

# ── 关系类型常量 ──

RelationType = Literal[
    "depends_on",
    "implements",
    "recommends",
    "conflicts_with",
    "alternative_to",
    "part_of",
    "extracted_from",
]

VALID_RELATION_TYPES: list[str] = [
    "depends_on",
    "implements",
    "recommends",
    "conflicts_with",
    "alternative_to",
    "part_of",
    "extracted_from",
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


class KGRelation(BaseModel):
    """知识图谱关系。"""

    id: str = ""
    source: str  # 源实体 ID
    target: str  # 目标实体 ID
    type: RelationType = "depends_on"
    reason: str = ""
    confidence: float = 0.9
    source_text_unit_id: str = ""
    workspace_id: str = ""


class TextUnit(BaseModel):
    """文本单元 — Chunk 与 Entity 之间的桥梁层。"""

    id: str = ""
    text: str
    entities: list[str] = Field(default_factory=list)  # 关联实体 ID
    relations: list[str] = Field(default_factory=list)  # 关联关系 ID
    section_path: str = ""
    embedding: list[float] = Field(default_factory=list)
    chunk_index: int = 0
    workspace_id: str = ""


class Claim(BaseModel):
    """声明性断言（Claims / Covariates）。

    从 TextUnit 中提取的对比/决策/规格/约束/预测类断言。
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
    text_unit_evidence: list[TextUnit] = Field(default_factory=list)
    community_summary: str = ""
    total_tokens: int = 0


class BuildStats(BaseModel):
    """知识图谱构建统计。"""

    entities: int = 0
    chunks: int = 0
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


class CommunityReport(BaseModel):
    """社区报告 — Global Search 的基础。"""

    id: str = ""
    community_id: str = ""
    level: int = 1
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    workspace_id: str = ""
