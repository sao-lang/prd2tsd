"""块 D — Orchestrator 单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph import StateGraph

from app.orchestrator.adapters import (
    AnalysisAdapter,
    EvaluationAdapter,
    GenerationAdapter,
    PlanningAdapter,
)
from app.orchestrator.human_review import HumanReviewNode
from app.orchestrator.iteration import IterationDecider
from app.orchestrator.routing import needs_review
from app.orchestrator.state import (
    OrchestratorState,
    TenantContext,
    make_initial_state,
)
from contracts.interfaces import (
    AnalysisResult,
    AnalysisResultDetail,
    EvaluationReportDetail,
    GenerationResultDetail,
    PlanningResultDetail,
)


# ── Fixtures ──


@pytest.fixture
def initial_state() -> OrchestratorState:
    """创建初始 OrchestratorState。"""
    return make_initial_state(
        task_id="test-1",
        prd_raw="# 测试 PRD\n## 功能\n1. 登录",
        prd_file_type="md",
    )


@pytest.fixture
def mock_analysis_graph() -> StateGraph:
    """创建 Mock Analysis Layer Graph。"""
    graph = MagicMock(spec=StateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "analysis_result": AnalysisResultDetail(
                project_name="测试项目",
                summary="测试摘要",
            ),
            "extracted_requirements": [],
            "extracted_constraints": [],
        }
    )
    return graph


@pytest.fixture
def mock_planning_graph() -> StateGraph:
    """创建 Mock Planning Layer Graph。"""
    graph = MagicMock(spec=StateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "planning_result": PlanningResultDetail(
                architecture_pattern="微服务",
            ),
            "component_decomposition": [],
            "tech_stack_choices": [],
        }
    )
    return graph


@pytest.fixture
def mock_generation_graph() -> StateGraph:
    """创建 Mock Generation Layer Graph。"""
    graph = MagicMock(spec=StateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "generation_result": GenerationResultDetail(
                content="# 技术方案\n测试内容",
                sections={"overview": "测试"},
            ),
            "section_contents": {"overview": "测试"},
        }
    )
    return graph


@pytest.fixture
def mock_evaluation_graph() -> StateGraph:
    """创建 Mock Evaluation Layer Graph。"""
    graph = MagicMock(spec=StateGraph)
    graph.ainvoke = AsyncMock(
        return_value={
            "evaluation_report": EvaluationReportDetail(
                overall_score=90.0,
                dimension_scores={"coverage": 90.0, "consistency": 85.0},
                conclusion="通过",
            ),
            "dimension_scores": {"coverage": 90.0, "consistency": 85.0},
        }
    )
    return graph


# ── Adapter 测试 ──


@pytest.mark.asyncio
async def test_analysis_adapter_runs_graph(
    initial_state: OrchestratorState,
    mock_analysis_graph: StateGraph,
):
    """验证 AnalysisAdapter 调用 Layer 并映射结果。"""
    adapter = AnalysisAdapter(mock_analysis_graph)
    result = await adapter.run(initial_state)

    mock_analysis_graph.ainvoke.assert_awaited_once()
    assert result["analysis_result"] is not None
    assert result["progress"] == 0.25
    assert result["task_id"] == "test-1"


@pytest.mark.asyncio
async def test_planning_adapter_runs_graph(
    initial_state: OrchestratorState,
    mock_planning_graph: StateGraph,
):
    """验证 PlanningAdapter 调用 Layer 并映射结果。"""
    adapter = PlanningAdapter(mock_planning_graph)
    result = await adapter.run(initial_state)

    mock_planning_graph.ainvoke.assert_awaited_once()
    assert result["planning_result"] is not None
    assert result["progress"] == 0.50


@pytest.mark.asyncio
async def test_generation_adapter_runs_graph(
    initial_state: OrchestratorState,
    mock_generation_graph: StateGraph,
):
    """验证 GenerationAdapter 调用 Layer 并映射结果。"""
    adapter = GenerationAdapter(mock_generation_graph)
    result = await adapter.run(initial_state)

    mock_generation_graph.ainvoke.assert_awaited_once()
    assert result["generation_result"] is not None
    assert result["progress"] == 0.75


@pytest.mark.asyncio
async def test_evaluation_adapter_runs_graph(
    initial_state: OrchestratorState,
    mock_evaluation_graph: StateGraph,
):
    """验证 EvaluationAdapter 调用 Layer 并映射结果。"""
    adapter = EvaluationAdapter(mock_evaluation_graph)
    result = await adapter.run(initial_state)

    mock_evaluation_graph.ainvoke.assert_awaited_once()
    assert result["evaluation_report"] is not None
    assert result["progress"] == 0.90


# ── IterationDecider 测试 ──


def test_iteration_accepts_high_score(initial_state: OrchestratorState):
    """验证高分时路由到 final_assembly。"""
    initial_state["evaluation_report"] = EvaluationReportDetail(
        overall_score=90.0,
        dimension_scores={"coverage": 90.0, "consistency": 85.0},
        conclusion="通过",
    )
    decider = IterationDecider()
    route = decider.run(initial_state)
    assert route == "final_assembly"


def test_iteration_regenerates_on_low_consistency(initial_state: OrchestratorState):
    """验证一致性低分时路由到 generation。"""
    initial_state["evaluation_report"] = EvaluationReportDetail(
        overall_score=75.0,
        dimension_scores={"consistency": 60.0, "feasibility": 80.0},
        conclusion="预警通过",
    )
    decider = IterationDecider()
    route = decider.run(initial_state)
    assert route == "generation"


def test_iteration_replans_on_low_feasibility(initial_state: OrchestratorState):
    """验证可行性低分时路由到 planning。"""
    initial_state["evaluation_report"] = EvaluationReportDetail(
        overall_score=72.0,
        dimension_scores={"consistency": 80.0, "feasibility": 55.0},
        conclusion="预警通过",
    )
    decider = IterationDecider()
    route = decider.run(initial_state)
    assert route == "planning"


def test_iteration_retries_on_low_score(initial_state: OrchestratorState):
    """验证低分时迭代重做。

    注意：iteration_count 递增在 EvaluationAdapter 中完成，
    IterationDecider 只负责根据已有值做路由决策。
    """
    initial_state["evaluation_report"] = EvaluationReportDetail(
        overall_score=50.0,
        dimension_scores={"coverage": 50.0},
        conclusion="不通过",
        critical_issues=[],
    )
    initial_state["iteration_count"] = 0
    decider = IterationDecider()
    route = decider.run(initial_state)
    # 低分且无 critical_issues → replan
    assert route == "planning"
    # iteration_count 不由 IterationDecider 递增（由 EvaluationAdapter 负责）
    assert initial_state["iteration_count"] == 0


def test_iteration_accepts_when_max_reached(initial_state: OrchestratorState):
    """验证达到最大迭代次数时强制接受。"""
    initial_state["evaluation_report"] = EvaluationReportDetail(
        overall_score=30.0,
        dimension_scores={},
        conclusion="不通过",
    )
    initial_state["iteration_count"] = 3
    initial_state["max_iterations"] = 3
    decider = IterationDecider()
    route = decider.run(initial_state)
    assert route == "final_assembly"


def test_iteration_asks_human_on_critical_issues(initial_state: OrchestratorState):
    """验证有 critical_issues 时请求人工介入。"""
    initial_state["evaluation_report"] = EvaluationReportDetail(
        overall_score=40.0,
        dimension_scores={},
        conclusion="不通过",
        critical_issues=[{"severity": "high", "description": "安全漏洞"}],
    )
    initial_state["iteration_count"] = 0
    decider = IterationDecider()
    route = decider.run(initial_state)
    assert route == "analysis_human_review"


# ── Routing 测试 ──


def test_needs_review_returns_review_needed(initial_state: OrchestratorState):
    """验证默认需要审核。"""
    initial_state["tenant_context"] = TenantContext()
    initial_state["user_role"] = "user"
    result = needs_review(initial_state)
    assert result == "review_needed"


def test_needs_review_skips_for_admin(initial_state: OrchestratorState):
    """验证 admin 角色跳过审核。"""
    initial_state["tenant_context"] = TenantContext()
    initial_state["user_role"] = "admin"
    result = needs_review(initial_state)
    assert result == "skip_review"


def test_needs_review_skips_with_auto_approve(initial_state: OrchestratorState):
    """验证 auto_approve 设置跳过审核。"""
    initial_state["tenant_context"] = TenantContext(
        settings={"auto_approve": True}
    )
    initial_state["user_role"] = "user"
    result = needs_review(initial_state)
    assert result == "skip_review"


# ── HumanReview 测试 ──


@patch("app.orchestrator.human_review.interrupt")
def test_human_review_interrupts(mock_interrupt, initial_state: OrchestratorState):
    """验证 HumanReviewNode 调用 interrupt。"""
    mock_interrupt.return_value = {"decision": "approved"}
    node = HumanReviewNode("analysis")
    result = node.run(initial_state)
    mock_interrupt.assert_called_once()
    assert result["status"] == "running"


@patch("app.orchestrator.human_review.interrupt")
def test_human_review_rejects(mock_interrupt, initial_state: OrchestratorState):
    """验证拒绝后状态变更为 paused。"""
    mock_interrupt.return_value = {"decision": "needs_changes", "comment": "需修改"}
    node = HumanReviewNode("analysis")
    result = node.run(initial_state)
    assert result["status"] == "paused"
    assert "需修改" in result["error_message"]


# ── TaskInfo / make_initial_state 测试 ──


def test_make_initial_state_defaults():
    """验证 make_initial_state 创建正确初始状态。"""
    state = make_initial_state(task_id="t1", prd_raw="test")
    assert state["task_id"] == "t1"
    assert state["prd_raw"] == "test"
    assert state["status"] == "running"
    assert state["progress"] == 0.0
    assert state["iteration_count"] == 0
    assert state["max_iterations"] == 3
    assert state["error_message"] == ""
    assert isinstance(state["tenant_context"], TenantContext)
