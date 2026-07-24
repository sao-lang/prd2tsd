"""Evaluation Layer Adapter — OrchestratorState ↔ EvaluationState 转换。"""

from __future__ import annotations

from langgraph.graph import StateGraph

from app.orchestrator.state import OrchestratorState


class EvaluationAdapter:
    """Evaluation Layer 的 Orchestrator Adapter。

    从 OrchestratorState 提取输入，调用 Evaluation Layer，
    将 EvaluationState 结果映射回 OrchestratorState。
    """

    def __init__(self, evaluation_graph: StateGraph) -> None:
        """初始化 Adapter。

        Args:
            evaluation_graph: 编译后的 Evaluation Layer StateGraph。
        """
        self.graph = evaluation_graph

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行 Evaluation Layer。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        # 1. 提取 Evaluation Layer 需要的输入
        evaluation_input = {
            "analysis_result": state.get("analysis_result"),
            "planning_result": state.get("planning_result"),
            "generation_result": state.get("generation_result"),
        }

        # 2. 调用 Evaluation Layer
        result = await self.graph.ainvoke(evaluation_input)

        # 3. 映射回 OrchestratorState
        state["evaluation_report"] = result.get("evaluation_report")
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        state["progress"] = 0.90

        return state
