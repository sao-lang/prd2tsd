"""Orchestrator 全局状态定义。

包含 OrchestratorConfig（静态配置）、OrchestratorState（TypedDict）、
OrchestratorRuntime（运行时上下文）、TenantContext、TaskInfo。

三层数据模型：
- Config: 启动时加载，只读
- State: LangGraph checkpoint 自动持久化
- Runtime: 每次请求从外部注入，不参与 checkpoint 序列化
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NotRequired

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from contracts.interfaces import (
    AnalysisResultDetail,
    ComponentDetail,
    ConstraintDetail,
    EvaluationReportDetail,
    GenerationResultDetail,
    PlanningResultDetail,
    RequirementDetail,
    TechChoiceDetail,
)


class OrchestratorConfig(BaseModel):
    """主编排器静态配置 — 从 pyproject.toml / env 加载后不变。"""

    max_iterations: int = 3
    evaluation_pass_threshold: float = 85.0
    evaluation_replan_threshold: float = 70.0


class OrchestratorRuntime:
    """运行时上下文 — 每次调用从外部注入，不参与 checkpoint 序列化。

    Attributes:
        db_session: 数据库会话（每个请求新建）。
        event_bus: SSE 事件总线引用。
        llm_gateway: LLM Gateway 实例。
        current_user_id: 当前用户 ID。
        current_workspace_id: 当前工作空间 ID。
        started_at: 请求开始时间。
    """

    def __init__(
        self,
        db_session: Any = None,
        event_bus: Any = None,
        llm_gateway: Any = None,
        current_user_id: str = "",
        current_workspace_id: str = "",
    ) -> None:
        """初始化运行时上下文。"""
        self.db_session = db_session
        self.event_bus = event_bus
        self.llm_gateway = llm_gateway
        self.current_user_id = current_user_id
        self.current_workspace_id = current_workspace_id
        self.started_at = datetime.utcnow()


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
    analysis_result: AnalysisResultDetail
    extracted_requirements: list[RequirementDetail]
    extracted_constraints: list[ConstraintDetail]

    # ── 块 C2 Planning ──
    planning_result: PlanningResultDetail
    component_decomposition: list[ComponentDetail]
    tech_stack_choices: list[TechChoiceDetail]

    # ── 块 C3 Generation ──
    generation_result: GenerationResultDetail
    section_contents: dict[str, str]
    export_formats: dict[str, str]

    # ── 块 C4 Evaluation ──
    evaluation_report: EvaluationReportDetail

    # ── 简单对话/知识查询响应（chat / knowledge_qa 路径）──
    chat_response: str

    # ── 控制字段 ──
    iteration_count: int
    max_iterations: int
    status: Literal["running", "paused", "complete", "failed", "clarification_needed"]
    error_message: str
    progress: float  # 0.0 ~ 1.0

    # ── 意图路由字段（由统一交互入口或 classify 节点写入）──
    intent: NotRequired[str]
    intent_confidence: NotRequired[float]
    intent_sub: NotRequired[str]

    # ── 会话记忆（Block F 记忆增强）──
    session_id: NotRequired[str]
    _history_messages: NotRequired[list[dict[str, str]]]  # 历史会话消息（retrieve/compress 节点消费）
    retrieved_memories: NotRequired[list[dict[str, Any]]]  # 记忆检索结果（chat/retrieve 节点消费）
    compressed_context: NotRequired[list[dict[str, str]]]  # 压缩后的上下文（save_session 持久化）


class TaskInfo(BaseModel):
    """任务信息（API 返回）。"""

    task_id: str
    status: str
    progress: float = 0.0
    stage: str = ""  # 当前阶段名称
    interrupt_stage: str = ""  # 被 interrupt 暂停的阶段
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
    max_iterations: int | None = None,
    tenant_context: TenantContext | None = None,
    history_messages: list[dict[str, str]] | None = None,
    session_id: str = "",
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
        max_iterations: 最大迭代次数（缺省取 OrchestratorConfig.max_iterations）。
        tenant_context: 多租户上下文。
        history_messages: 历史会话消息列表（Phase 3: 记忆增强输入）。
        session_id: 关联会话 ID（可选，用于记忆检索与会话持久化绑定）。

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
        "session_id": session_id,
        "tenant_context": tenant_context or TenantContext(),
        "knowledge_context": None,
        "analysis_result": AnalysisResultDetail(project_name="", summary=""),
        "extracted_requirements": [],
        "extracted_constraints": [],
        "planning_result": PlanningResultDetail(),
        "component_decomposition": [],
        "tech_stack_choices": [],
        "generation_result": GenerationResultDetail(),
        "section_contents": {},
        "export_formats": {},
        "evaluation_report": EvaluationReportDetail(),
        "chat_response": "",
        "iteration_count": 0,
        "max_iterations": max_iterations if max_iterations is not None else OrchestratorConfig().max_iterations,
        "status": "running",
        "error_message": "",
        "progress": 0.0,
        # Phase 3: 记忆增强 — 供 retrieve_memory / compress_memory 节点消费
        "_history_messages": history_messages or [],
    }
