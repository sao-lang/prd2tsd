"""Agent 评测模块单元测试（mock runner/LLM）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.evaluation.agent import AgentEvaluator
from app.evaluation.agent.models import AgentTask

SAMPLE_TASK = AgentTask(
    id="t1",
    task="生成方案",
    prd_input="PRD 文本",
    expected_key_points=["架构", "数据库"],
    rubric={"implementability": "方案是否可落地（0-10）", "consistency": "各章节是否自洽（0-10）"},
)


async def test_evaluate_process_metrics() -> None:
    """验证 L3 过程指标汇总。"""

    async def runner(task: AgentTask) -> dict:
        """模拟任务执行。"""
        return {
            "completed": True,
            "iterations": 2,
            "human_review_required": False,
            "result": {"status": "complete"},
        }

    evaluator = AgentEvaluator(runner=runner)
    with patch.object(
        evaluator,
        "judge_result",
        AsyncMock(return_value=({"implementability": 8.0, "consistency": 7.0}, {})),
    ):
        report = await evaluator.evaluate(
            [SAMPLE_TASK, SAMPLE_TASK.model_copy(update={"id": "t2"})]
        )

    assert report.completion_rate == 1.0
    assert report.avg_iterations == 2.0
    assert report.human_review_rate == 0.0
    assert report.avg_judge_score == 7.5
    assert len(report.tasks) == 2


async def test_evaluate_failure_metrics() -> None:
    """验证任务失败与人工介入统计。"""

    async def runner(task: AgentTask) -> dict:
        """模拟失败任务。"""
        return {
            "completed": False,
            "iterations": 3,
            "human_review_required": True,
            "result": {},
        }

    evaluator = AgentEvaluator(runner=runner)
    with patch.object(evaluator, "judge_result", AsyncMock(return_value=({}, {}))):
        report = await evaluator.evaluate([SAMPLE_TASK])

    assert report.completion_rate == 0.0
    assert report.avg_iterations == 3.0
    assert report.human_review_rate == 1.0
    assert report.avg_judge_score == 0.0


async def test_judge_result_parses_json() -> None:
    """验证 judge 响应 JSON 解析。"""
    evaluator = AgentEvaluator()
    resp = MagicMock()
    resp.content = (
        '{"scores": {"implementability": 8, "consistency": 7}, '
        '"comments": {"implementability": "方案可落地"}}'
    )
    with patch("app.evaluation.agent.evaluator.gateway") as mock_gw:
        mock_gw.complete = AsyncMock(return_value=resp)
        scores, comments = await evaluator.judge_result(
            SAMPLE_TASK,
            {"result": {"status": "complete", "sections": []}},
        )

    assert scores["implementability"] == 8.0
    assert scores["consistency"] == 7.0
    assert comments["implementability"] == "方案可落地"


async def test_judge_result_invalid_json() -> None:
    """验证 judge 响应非 JSON 时优雅降级。"""
    evaluator = AgentEvaluator()
    resp = MagicMock()
    resp.content = "不是 JSON"
    with patch("app.evaluation.agent.evaluator.gateway") as mock_gw:
        mock_gw.complete = AsyncMock(return_value=resp)
        scores, comments = await evaluator.judge_result(
            SAMPLE_TASK,
            {"result": {}},
        )

    assert scores == {}
    assert comments == {}


def test_empty_tasks_report() -> None:
    """验证空任务集的报告结构。"""
    evaluator = AgentEvaluator()
    report = evaluator._build_report([], None)
    assert report.completion_rate == 0.0
    assert report.tasks == []
