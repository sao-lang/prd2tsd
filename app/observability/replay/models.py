"""Agent 行为回放数据模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class DecisionRecord(BaseModel):
    """单次决策记录。"""

    id: str = ""
    task_id: str
    trace_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_name: str = ""
    node_name: str = ""
    iteration_count: int = 0
    input_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_prompt: str = ""
    input_tools: list[dict] = Field(default_factory=list)
    llm_response: str = ""
    tool_calls: list[dict] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    output_state_diff: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float = 0.0
    tokens_consumed: int = 0
    decision_summary: str = ""


class TraceTree(BaseModel):
    """全链路追踪树 — 一个 task 的完整决策链。"""

    task_id: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    total_duration_ms: float = 0.0
    nodes: list[DecisionRecord] = Field(default_factory=list)
    edges: list[tuple[str, str, str]] = Field(default_factory=list)
