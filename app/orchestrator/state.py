"""Orchestrator 全局状态定义。

包含 OrchestratorState（TypedDict）、TenantContext、TaskInfo。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResult,
    Component,
    Constraint,
    EvaluationReportDetail,
    GenerationResultDetail,
    PlanningResult,
    Requirement,
    TechChoice,
)


class TenantContext(BaseModel):
    """多租户上下文 — 贯穿所有 Layer 的租户隔离信息。"""

    organization_id: str = ""
    workspace_id: str = ""
    knowledge_scope: str = "workspace"  # workspace / org / global
    settings: dict[str, Any] = Field(default_factory=dict)


class OrchestratorState(TypedDict):
    """主编排器状态 — 串联 4 个 Layer 的全局状态。"""

    # ── 输入 ──
    task_id: str
    prd_raw: str
    prd_file_type: str  # md / pdf / docx
    workspace_id: str
    user_id: str
    user_role: str
    permissions: list[str]

    # ── 多租户上下文 ──
    tenant_context: TenantContext

    # ── 块 B 知识检索 ──
    knowledge_context: Any  # knowledge_layer.models.RetrievalContext | None

    # ── 块 C1 Analysis ──
    analysis_result: AnalysisResult
    extracted_requirements: list[Requirement]
    extracted_constraints: list[Constraint]

    # ── 块 C2 Planning ──
    planning_result: PlanningResult
    component_decomposition: list[Component]
    tech_stack_choices: list[TechChoice]

    # ── 块 C3 Generation ──
    generation_result: GenerationResultDetail
    section_contents: dict[str, str]

    # ── 块 C4 Evaluation ──
    evaluation_report: EvaluationReportDetail

    # ── 控制字段 ──
    iteration_count: int
    max_iterations: int
    status: Literal["running", "paused", "complete", "failed"]
    error_message: str
    progress: float  # 0.0 ~ 1.0


class TaskInfo(BaseModel):
    """任务信息（API 返回）。"""

    task_id: str
    status: str
    progress: float = 0.0
    result: GenerationResultDetail | None = None
    evaluation: EvaluationReportDetail | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""


def make_initial_state(
    task_id: str,
    prd_raw: str,
    prd_file_type: str = "md",
    workspace_id: str = "",
    user_id: str = "",
    user_role: str = "",
    permissions: list[str] | None = None,
    max_iterations: int = 3,
    tenant_context: TenantContext | None = None,
) -> OrchestratorState:
    """构造初始 OrchestratorState。

    Args:
        task_id: 任务 ID。
        prd_raw: PRD 原始内容。
        prd_file_type: 文件类型。
        workspace_id: 工作空间 ID。
        user_id: 用户 ID。
        user_role: 用户角色。
        permissions: 用户权限列表。
        max_iterations: 最大迭代次数。
        tenant_context: 多租户上下文。

    Returns:
        初始化的 OrchestratorState。
    """
    return {
        "task_id": task_id,
        "prd_raw": prd_raw,
        "prd_file_type": prd_file_type,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "user_role": user_role,
        "permissions": permissions or [],
        "tenant_context": tenant_context or TenantContext(),
        "knowledge_context": None,
        "analysis_result": AnalysisResult(
            project_name="",
            summary="",
            requirements=[],
            constraints=[],
        ),
        "extracted_requirements": [],
        "extracted_constraints": [],
        "planning_result": PlanningResult(
            architecture_pattern="",
            tech_stack=[],
            components=[],
        ),
        "component_decomposition": [],
        "tech_stack_choices": [],
        "generation_result": GenerationResultDetail(),
        "section_contents": {},
        "evaluation_report": EvaluationReportDetail(),
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "status": "running",
        "error_message": "",
        "progress": 0.0,
    }
