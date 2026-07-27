"""Prompt 版本管理数据模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    """Prompt 版本。"""

    id: str = ""
    name: str  # "analysis.requirement"
    version: int  # 自增版本号
    content: str  # Prompt 文本
    hash: str = ""  # SHA-256 内容哈希
    author: str = ""
    changelog: str = ""
    is_active: bool = False
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ABTestConfig(BaseModel):
    """A/B 测试配置。"""

    prompt_name: str
    version_a: int
    version_b: int
    traffic_split: float = 0.5  # A 版本流量占比
    metric: str = "eval_score"
    is_active: bool = False
