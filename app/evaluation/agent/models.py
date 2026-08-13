"""Agent 评测数据模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    """Agent 评测任务。

    Attributes:
        id: 任务唯一 ID。
        task: 任务描述。
        prd_input: PRD 文本或 fixture 路径占位。
        expected_key_points: 期望覆盖的关键点。
        rubric: 评分标准（维度 → 评分说明）。
        expected_max_iterations: 期望最大迭代轮数。
    """

    id: str
    task: str
    prd_input: str = ""
    expected_key_points: list[str] = Field(default_factory=list)
    rubric: dict[str, Any] = Field(default_factory=dict)
    expected_max_iterations: int = 2


class AgentTaskScore(BaseModel):
    """单任务评测结果。

    Attributes:
        task_id: 任务 ID。
        completed: 是否成功完成。
        iterations: 迭代轮数。
        human_review_required: 是否需人工审核。
        duration_s: 执行耗时（秒）。
        judge_scores: rubric 各维度得分。
        judge_text: rubric 各维度评语。
    """

    task_id: str
    completed: bool = False
    iterations: int = 0
    human_review_required: bool = False
    duration_s: float = 0.0
    judge_scores: dict[str, float] = Field(default_factory=dict)
    judge_text: dict[str, str] = Field(default_factory=dict)


class AgentEvalReport(BaseModel):
    """Agent 评测报告（L3 过程指标 + L4 结果质量汇总）。

    Attributes:
        completion_rate: 任务完成率。
        avg_iterations: 平均迭代轮数。
        human_review_rate: 人工介入率。
        avg_judge_score: judge 平均分。
        tasks: 按任务明细。
        config: 评测配置。
        timestamp: 报告生成时间。
    """

    completion_rate: float = 0.0
    avg_iterations: float = 0.0
    human_review_rate: float = 0.0
    avg_judge_score: float = 0.0
    tasks: list[AgentTaskScore] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
