"""Analysis Layer Adapter — OrchestratorState ↔ AnalysisState 转换。"""

from __future__ import annotations

from langgraph.graph import StateGraph

from app.orchestrator.state import OrchestratorState


class AnalysisAdapter:
    """Analysis Layer 的 Orchestrator Adapter。

    从 OrchestratorState 提取输入，调用 Analysis Layer，
    将 AnalysisState 结果映射回 OrchestratorState。
    """

    def __init__(self, analysis_graph: StateGraph) -> None:
        """初始化 Adapter。

        Args:
            analysis_graph: 编译后的 Analysis Layer StateGraph。
        """
        self.graph = analysis_graph

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行 Analysis Layer。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        # 1. 提取 Analysis Layer 需要的输入
        # 注意：AnalysisState 只接收 prd_raw，不接收 prd_file_type
        analysis_input: dict = {
            "prd_raw": state["prd_raw"],
        }

        # 2. 如果有 knowledge_context，注入到 analysis_input
        kn_ctx = state.get("knowledge_context")
        if kn_ctx is not None:
            analysis_input["knowledge_context"] = kn_ctx

        # 3. 调用 Analysis Layer
        result = await self.graph.ainvoke(analysis_input)

        # 4. 映射回 OrchestratorState
        state["analysis_result"] = result.get("analysis_result")
        state["extracted_requirements"] = result.get("extracted_requirements", [])
        state["extracted_constraints"] = result.get("extracted_constraints", [])
        state["progress"] = 0.25

        return state
