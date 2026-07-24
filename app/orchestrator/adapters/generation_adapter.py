"""Generation Layer Adapter — OrchestratorState ↔ GenerationState 转换。"""

from __future__ import annotations

from langgraph.graph import StateGraph

from app.orchestrator.state import OrchestratorState


class GenerationAdapter:
    """Generation Layer 的 Orchestrator Adapter。

    从 OrchestratorState 提取输入，调用 Generation Layer，
    将 GenerationState 结果映射回 OrchestratorState。
    """

    def __init__(self, generation_graph: StateGraph) -> None:
        """初始化 Adapter。

        Args:
            generation_graph: 编译后的 Generation Layer StateGraph。
        """
        self.graph = generation_graph

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行 Generation Layer。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        # 1. 提取 Generation Layer 需要的输入
        generation_input = {
            "planning_result": state.get("planning_result"),
            "analysis_result": state.get("analysis_result"),
        }

        # 2. 调用 Generation Layer
        result = await self.graph.ainvoke(generation_input)

        # 3. 映射回 OrchestratorState
        state["generation_result"] = result.get("generation_result")
        state["section_contents"] = result.get("section_contents", {})
        state["progress"] = 0.75

        return state
