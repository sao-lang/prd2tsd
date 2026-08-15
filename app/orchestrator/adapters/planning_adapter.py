"""Planning Layer Adapter — OrchestratorState ↔ PlanningState 转换。"""

from __future__ import annotations

from langgraph.graph import StateGraph

from app.observability.replay.recorder import DecisionRecorder, record_node_execution
from app.orchestrator.state import OrchestratorState


class PlanningAdapter:
    """Planning Layer 的 Orchestrator Adapter。

    从 OrchestratorState 提取输入，调用 Planning Layer，
    将 PlanningState 结果映射回 OrchestratorState。
    """

    def __init__(self, planning_graph: StateGraph, recorder: DecisionRecorder | None = None) -> None:
        """初始化 Adapter。

        Args:
            planning_graph: 编译后的 Planning Layer StateGraph。
            recorder: DecisionRecorder 实例（可选，用于决策回放）。
        """
        self.graph = planning_graph
        self.recorder = recorder

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行 Planning Layer。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        # 1. 提取 Planning Layer 需要的输入
        planning_input: dict = {
            "analysis_result": state.get("analysis_result"),
            "knowledge_context": state.get("knowledge_context"),
        }

        # P0.1: 注入评测反馈（迭代循环时）
        eval_report = state.get("evaluation_report")
        if eval_report is not None:
            if hasattr(eval_report, "critical_issues"):
                planning_input["evaluation_feedback"] = {
                    "issues": list(eval_report.critical_issues),
                    "recommendations": list(eval_report.recommendations),
                    "overall_score": float(eval_report.overall_score),
                }
            else:
                planning_input["evaluation_feedback"] = {
                    "issues": eval_report.get("critical_issues", []),
                    "recommendations": eval_report.get("recommendations", []),
                    "overall_score": float(eval_report.get("overall_score", 0.0)),
                }

        # 2. 调用 Planning Layer
        result = await self.graph.ainvoke(planning_input)

        # 3. 映射回 OrchestratorState
        state["planning_result"] = result.get("planning_result")
        state["component_decomposition"] = result.get("component_decomposition", [])
        state["tech_stack_choices"] = result.get("tech_stack_choices", [])
        state["progress"] = 0.50

        # Block F: 记录决策（供回放分析）
        if self.recorder is not None:
            await record_node_execution(
                self.recorder,
                state.get("task_id", ""),
                "planning",
                {"analysis_ready": state.get("analysis_result") is not None},
                str(state.get("prd_raw", ""))[:500],
                {
                    "planning_result": str(state.get("planning_result", ""))[:200],
                    "components": len(state.get("component_decomposition", [])),
                    "tech_choices": len(state.get("tech_stack_choices", [])),
                },
            )

        return state
