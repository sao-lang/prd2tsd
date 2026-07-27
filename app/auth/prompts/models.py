"""租户 Prompt 数据模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class TenantPrompt(BaseModel):
    """租户级 Prompt 模板。"""

    id: str = ""
    organization_id: str
    agent_name: str  # analysis / planning / generation / evaluation
    node_name: str  # requirement_extractor / pattern_recommend ...
    template: str  # Jinja2 模板
    variables: dict[str, str] = Field(default_factory=dict)  # 默认变量值
    version: int = 1
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
