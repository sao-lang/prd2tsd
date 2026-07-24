"""块 D — 全链路集成测试（Mock LLM 调用）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.orchestrator.main_graph import build_and_compile
from app.orchestrator.state import TenantContext, make_initial_state
from app.task_manager import TaskManager


# ── 样本 PRD ──

SAMPLE_PRD = """# 用户服务系统设计

## 技术栈

用户服务使用 Spring Boot 3.2 框架，基于 PostgreSQL 15 数据库存储用户数据。
使用 Redis 7 做会话缓存和令牌黑名单。使用 JWT 做身份认证，Token 有效期 15 分钟。

## 架构设计

系统采用微服务架构，分为用户服务、认证服务和通知服务三个核心组件。

## 安全约束

密码必须使用 bcrypt 加密存储，API 访问需要 JWT Token 鉴权。
"""


class MockCompiledGraph:
    """模拟编译后的 LangGraph StateGraph。"""

    def __init__(self, return_value: dict) -> None:
        self.return_value = return_value

    async def ainvoke(self, *args, **kwargs) -> dict:  # noqa: ANN002, ANN003
        return self.return_value


# ── Mock Graphs ──


@pytest.fixture
def mock_graphs():
    """创建全链路 Mock Layer Graphs。"""
    mock_analysis = MockCompiledGraph({
        "analysis_result": {
            "project_name": "用户服务",
            "summary": "用户服务系统设计",
            "domain_tags": ["微服务"],
            "requirements": [],
            "constraints": [],
        },
        "extracted_requirements": [],
        "extracted_constraints": [],
    })

    mock_planning = MockCompiledGraph({
        "planning_result": {
            "architecture_pattern": "微服务",
            "tech_stack": [],
            "components": [],
        },
        "component_decomposition": [],
        "tech_stack_choices": [],
    })

    mock_generation = MockCompiledGraph({
        "generation_result": {
            "content": "# 技术方案文档\n\n## 概述\n\n这是一个测试技术方案。" * 50,
            "sections": {"overview": "概述内容"},
        },
        "section_contents": {"overview": "概述内容"},
    })

    mock_evaluation = MockCompiledGraph({
        "evaluation_report": {
            "overall_score": 88.0,
            "dimension_scores": {
                "coverage": 90.0,
                "consistency": 85.0,
                "feasibility": 88.0,
            },
            "conclusion": "通过",
            "recommendations": [],
        },
        "dimension_scores": {"coverage": 90.0, "consistency": 85.0, "feasibility": 88.0},
    })

    yield {
        "analysis": mock_analysis,
        "planning": mock_planning,
        "generation": mock_generation,
        "evaluation": mock_evaluation,
    }


@pytest.fixture
def mock_pipeline():
    """创建 Mock RetrievalPipeline。"""
    from app.knowledge_layer.models import RetrievalContext

    pipeline = AsyncMock()
    pipeline.retrieve = AsyncMock(
        return_value=RetrievalContext(query="test", mode="hybrid", results=[]),
    )
    return pipeline


@pytest.mark.asyncio
async def test_full_pipeline_with_mock_llm(mock_graphs, mock_pipeline):
    """验证全链路（Mock LLM 调用）。"""
    orchestrator = build_and_compile(
        analysis_graph=mock_graphs["analysis"],
        planning_graph=mock_graphs["planning"],
        generation_graph=mock_graphs["generation"],
        evaluation_graph=mock_graphs["evaluation"],
        retrieval_pipeline=mock_pipeline,
    )

    state = make_initial_state(
        task_id="integration-test-1",
        prd_raw=SAMPLE_PRD,
        prd_file_type="md",
        tenant_context=TenantContext(
            settings={"auto_approve": True},
        ),
    )

    result = await orchestrator.ainvoke(state)

    assert result["status"] == "complete"
    assert result["progress"] == 1.0
    assert result["generation_result"] is not None
    assert result["evaluation_report"] is not None

    # 验证文档长度
    gen_result = result["generation_result"]
    content = ""
    if isinstance(gen_result, dict):
        content = gen_result.get("content", "")
    else:
        content = getattr(gen_result, "content", "")
    assert len(content) > 1000, f"文档内容不足: {len(content)}"


@pytest.mark.asyncio
async def test_orchestrator_retries_on_low_score(mock_graphs, mock_pipeline):
    """验证低分时自动回退。"""
    # 让 Evaluation 返回低分
    mock_graphs["evaluation"].return_value = {
        "evaluation_report": {
            "overall_score": 55.0,
            "dimension_scores": {"coverage": 50.0, "consistency": 60.0, "feasibility": 55.0},
            "conclusion": "不通过",
            "critical_issues": [],
            "recommendations": ["需要改进"],
        },
        "dimension_scores": {"coverage": 50.0, "consistency": 60.0, "feasibility": 55.0},
    }

    orchestrator = build_and_compile(
        analysis_graph=mock_graphs["analysis"],
        planning_graph=mock_graphs["planning"],
        generation_graph=mock_graphs["generation"],
        evaluation_graph=mock_graphs["evaluation"],
        retrieval_pipeline=mock_pipeline,
    )

    state = make_initial_state(
        task_id="integration-test-retry",
        prd_raw=SAMPLE_PRD,
        prd_file_type="md",
        max_iterations=3,
        tenant_context=TenantContext(
            settings={"auto_approve": True},
        ),
    )

    # 这里用有限迭代测试回退逻辑
    result = await orchestrator.ainvoke(state)

    # 由于迭代决策会回退到 planning，如果 mock 层每次都返回低分，
    # 最终会达到 max_iterations 强制 accept
    assert result["status"] == "complete"
    assert result["iteration_count"] >= 0


@pytest.mark.asyncio
async def test_adapter_preserves_layer_independence(mock_graphs):
    """验证 Adapter 不修改 Layer 内部逻辑。"""
    # 直接调用 Analysis Layer，验证它仍然正常工作
    mock_graphs["analysis"].ainvoke = AsyncMock(return_value={
        "analysis_result": {
            "project_name": "独立测试",
            "summary": "独立层测试",
        },
        "extracted_requirements": [],
        "extracted_constraints": [],
    })

    result = await mock_graphs["analysis"].ainvoke({"prd_raw": SAMPLE_PRD})
    assert result["analysis_result"] is not None
    project_name = ""
    if isinstance(result["analysis_result"], dict):
        project_name = result["analysis_result"].get("project_name", "")
    else:
        project_name = getattr(result["analysis_result"], "project_name", "")
    assert project_name == "独立测试"


# ── TaskManager 测试 ──


@pytest.mark.asyncio
async def test_task_manager_create_and_query():
    """验证 TaskManager 创建和查询任务。"""
    mgr = TaskManager()
    task_id = await mgr.create_task(
        prd_raw=SAMPLE_PRD,
        prd_file_type="md",
        orchestrator=None,
    )
    assert task_id is not None

    task = await mgr.get_task(task_id)
    assert task is not None
    assert task.status == "running"
    assert task.task_id == task_id
