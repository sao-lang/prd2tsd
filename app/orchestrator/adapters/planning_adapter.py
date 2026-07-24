"""Planning Layer Adapter — OrchestratorState ↔ PlanningState 转换。"""

from __future__ import annotations

from langgraph.graph import StateGraph

from app.orchestrator.state import OrchestratorState


class PlanningAdapter:
    """Planning Layer 的 Orchestrator Adapter。

    从 OrchestratorState 提取输入，调用 Planning Layer，
    将 PlanningState 结果映射回 OrchestratorState。
    """

    def __init__(self, planning_graph: StateGraph) -> None:
        """初始化 Adapter。

        Args:
            planning_graph: 编译后的 Planning Layer StateGraph。
        """
        self.graph = planning_graph

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行 Planning Layer。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        # 1. 提取 Planning Layer 需要的输入
        planning_input = {
            "analysis_result": state.get("analysis_result"),
            "knowledge_context": state.get("knowledge_context"),
        }

        # 2. 调用 Planning Layer
        result = await self.graph.ainvoke(planning_input)

        # 3. 映射回 OrchestratorState
        state["planning_result"] = result.get("planning_result")
        state["component_decomposition"] = result.get("component_decomposition", [])
        state["tech_stack_choices"] = result.get("tech_stack_choices", [])
        state["progress"] = 0.50

        return state
