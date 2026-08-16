"""Agent 评测器 — 过程指标（L3）+ rubric 化 LLM-judge（L4）。"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logger import get_logger
from app.evaluation.agent.models import AgentEvalReport, AgentTask, AgentTaskScore
from app.llm_gateway import gateway

logger = get_logger("prd2tsd.eval.agent")

# 任务执行器类型：接收 AgentTask，返回执行摘要 dict。
TaskRunner = Callable[[AgentTask], Awaitable[dict[str, Any]]]

_JUDGE_PROMPT = """你是资深技术方案评审专家。请根据以下评分标准，对生成的技术方案进行评分。

评分标准（rubric）：
{rubric}

待评方案（最终状态）：
{result}

请返回严格的 JSON（不要包含任何其他文本）：
{{"scores": {{"<评分维度>": <0-10 的数字>}}, "comments": {{"<评分维度>": "<一句话评语>"}}}}"""


class AgentEvaluator:
    """Agent 评测器。

    对每个任务：
    - L3 过程指标：完成率、迭代轮数、是否需人工 review、耗时
    - L4 结果质量：按 rubric 用 judge 模型打分（结构化 JSON 解析）

    Usage:
        evaluator = AgentEvaluator(runner=my_runner)
        report = await evaluator.evaluate(tasks)
    """

    def __init__(self, runner: TaskRunner | None = None) -> None:
        """初始化评测器。

        Args:
            runner: 任务执行器（接收 AgentTask，返回执行摘要 dict）。
                未提供时使用默认主编排执行器。
        """
        self._runner = runner or self._default_runner

    async def _default_runner(self, task: AgentTask) -> dict[str, Any]:
        """默认执行器：通过主编排图运行任务。

        Args:
            task: Agent 评测任务。

        Returns:
            执行摘要 dict（completed/iterations/human_review_required/result）。
        """
        from langchain_core.runnables import RunnableConfig

        from app.api.deps import get_orchestrator
        from app.orchestrator.state import make_initial_state

        orchestrator = get_orchestrator()
        initial = make_initial_state(
            task_id=f"eval_{task.id}",
            prd_raw=task.prd_input,
            prd_file_type="md",
            workspace_id="",
        )
        config: RunnableConfig = {"configurable": {"thread_id": f"eval_{task.id}"}}
        final_state: dict[str, Any] = {}
        async for step in orchestrator.astream(initial, config):
            final_state = step if isinstance(step, dict) else {}
        return {
            "completed": final_state.get("status") == "complete",
            "iterations": int(final_state.get("iteration_count", 0)),
            "human_review_required": bool(final_state.get("needs_review", False)),
            "result": final_state,
        }

    async def judge_result(
        self,
        task: AgentTask,
        result: dict[str, Any],
    ) -> tuple[dict[str, float], dict[str, str]]:
        """按 rubric 用 judge 模型打分。

        Args:
            task: Agent 任务。
            result: 任务执行摘要。

        Returns:
            (scores, comments) 两个 dict；rubric 为空或解析失败时返回空 dict。
        """
        if not task.rubric:
            return {}, {}

        rubric_text = json.dumps(task.rubric, ensure_ascii=False, indent=2)
        result_state = result.get("result", {})
        if isinstance(result_state, (dict, list)):
            result_text = json.dumps(result_state, ensure_ascii=False, default=str)[:4000]
        else:
            result_text = str(result_state)[:4000]

        try:
            resp = await gateway.complete(
                prompt=_JUDGE_PROMPT.format(rubric=rubric_text, result=result_text),
                task_type="evaluation_scoring",
                layer="evaluation",
                node="agent_judge",
                temperature=0,
                max_tokens=1024,
            )
            data = json.loads(resp.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Agent judge 响应解析失败: task=%s, err=%s", task.id, exc)
            return {}, {}

        scores = {k: self._to_float(v) for k, v in data.get("scores", {}).items()}
        comments = {k: str(v) for k, v in data.get("comments", {}).items()}
        return scores, comments

    async def evaluate(
        self,
        tasks: list[AgentTask],
        config: dict[str, Any] | None = None,
    ) -> AgentEvalReport:
        """执行 Agent 评测。

        Args:
            tasks: Agent 任务列表。
            config: 评测配置（记录到报告）。

        Returns:
            AgentEvalReport。
        """
        task_scores: list[AgentTaskScore] = []
        for task in tasks:
            start = time.monotonic()
            outcome = await self._runner(task)
            duration_s = time.monotonic() - start

            judge_scores, judge_comments = await self.judge_result(task, outcome)
            task_scores.append(
                AgentTaskScore(
                    task_id=task.id,
                    completed=bool(outcome.get("completed", False)),
                    iterations=int(outcome.get("iterations", 0)),
                    human_review_required=bool(outcome.get("human_review_required", False)),
                    duration_s=round(duration_s, 2),
                    judge_scores=judge_scores,
                    judge_text=judge_comments,
                )
            )

        return self._build_report(task_scores, config)

    @staticmethod
    def _build_report(
        task_scores: list[AgentTaskScore],
        config: dict[str, Any] | None,
    ) -> AgentEvalReport:
        """汇总报告。

        Args:
            task_scores: 各任务得分。
            config: 评测配置。

        Returns:
            AgentEvalReport。
        """
        n = len(task_scores)
        if n == 0:
            return AgentEvalReport(config=config or {})
        completion_rate = sum(1 for t in task_scores if t.completed) / n
        avg_iterations = sum(t.iterations for t in task_scores) / n
        review_rate = sum(1 for t in task_scores if t.human_review_required) / n
        judge_sums = [sum(t.judge_scores.values()) / len(t.judge_scores) for t in task_scores if t.judge_scores]
        avg_judge = (sum(judge_sums) / len(judge_sums)) if judge_sums else 0.0
        return AgentEvalReport(
            completion_rate=round(completion_rate, 3),
            avg_iterations=round(avg_iterations, 2),
            human_review_rate=round(review_rate, 3),
            avg_judge_score=round(avg_judge, 2),
            tasks=task_scores,
            config=config or {},
        )

    @staticmethod
    def _to_float(value: Any) -> float:
        """安全转 float。

        Args:
            value: 任意值。

        Returns:
            float 值，无效时返回 0.0。
        """
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0
