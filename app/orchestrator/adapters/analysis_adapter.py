"""Analysis Layer Adapter — OrchestratorState ↔ AnalysisState 转换。"""

from __future__ import annotations

from langgraph.graph import StateGraph

from app.observability.replay.recorder import DecisionRecorder, record_node_execution
from app.orchestrator.state import OrchestratorState


class AnalysisAdapter:
    """Analysis Layer 的 Orchestrator Adapter。

    从 OrchestratorState 提取输入，调用 Analysis Layer，
    将 AnalysisState 结果映射回 OrchestratorState。
    """

    def __init__(self, analysis_graph: StateGraph, recorder: DecisionRecorder | None = None) -> None:
        """初始化 Adapter。

        Args:
            analysis_graph: 编译后的 Analysis Layer StateGraph。
            recorder: DecisionRecorder 实例（可选，用于决策回放）。
        """
        self.graph = analysis_graph
        self.recorder = recorder

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行 Analysis Layer。

        Block F: 集成 PromptManager 加载租户自定义 System Prompt。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        # 1. 提取 Analysis Layer 需要的输入
        analysis_input: dict = {
            "prd_raw": state["prd_raw"],
        }

        # Block F: 加载租户自定义 Prompt
        from app.core.logger import get_logger
        from app.orchestrator.state import TenantContext
        _log = get_logger("prd2tsd.analysis_adapter")
        tenant_ctx = state.get("tenant_context")
        if isinstance(tenant_ctx, TenantContext):
            org_id = tenant_ctx.organization_id
            _settings = tenant_ctx.settings
        elif isinstance(tenant_ctx, dict):
            org_id = tenant_ctx.get("organization_id", "")
            _settings = tenant_ctx.get("settings", {})
        else:
            org_id = ""
            _settings = {}
        if org_id:
            try:
                from app.auth.prompts.manager import PromptManager
                pm = PromptManager()
                system_prompt = await pm.get_prompt(
                    organization_id=org_id,
                    agent_name="analysis",
                    node_name="requirement",
                    extra_vars={
                        "company_name": _settings.get("company_name", ""),
                        "industry": _settings.get("industry", ""),
                    },
                )
                if system_prompt:
                    analysis_input["system_prompt"] = system_prompt
            except Exception as e:
                _log.warning("加载租户 Prompt 失败 (org=%s): %s", org_id, e)

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

        # Block F: 记录决策（供回放分析）
        if self.recorder is not None:
            await record_node_execution(
                self.recorder,
                state.get("task_id", ""),
                "analysis",
                {"prd_raw_len": len(state.get("prd_raw", "")), "has_knowledge": kn_ctx is not None},
                str(state.get("prd_raw", ""))[:500],
                {
                    "analysis_result": str(state.get("analysis_result", ""))[:200],
                    "requirements": len(state.get("extracted_requirements", [])),
                    "constraints": len(state.get("extracted_constraints", [])),
                },
            )

        return state
