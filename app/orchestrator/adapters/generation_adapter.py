"""Generation Layer Adapter — OrchestratorState ↔ GenerationState 转换。"""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph.state import CompiledStateGraph

from app.observability.replay.recorder import DecisionRecorder, record_node_execution
from app.orchestrator.state import OrchestratorState
from contracts.interfaces import GenerationResultDetail


class GenerationAdapter:
    """Generation Layer 的 Orchestrator Adapter。

    从 OrchestratorState 提取输入，调用 Generation Layer，
    将 GenerationState 结果映射回 OrchestratorState。
    """

    def __init__(
        self,
        generation_graph: CompiledStateGraph[Any, Any, Any, Any],
        recorder: DecisionRecorder | None = None,
    ) -> None:
        """初始化 Adapter。

        Args:
            generation_graph: 编译后的 Generation Layer StateGraph。
            recorder: DecisionRecorder 实例（可选，用于决策回放）。
        """
        self.graph = generation_graph
        self.recorder = recorder

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行 Generation Layer。

        Block F: 集成 PromptManager 加载租户自定义 System Prompt。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        # 1. 提取 Generation Layer 需要的输入
        generation_input: dict[str, Any] = {
            "planning_result": state.get("planning_result"),
            "analysis_result": state.get("analysis_result"),
            # P0.1: 保留已有章节内容（迭代续写时用）
            "section_contents": state.get("section_contents", {}),
            # Phase 4: 传递导出格式配置（PDF/DOCX 等）
            "export_formats": state.get("export_formats", {}),
            # Block E: SSE 流式推送需要 task_id
            "task_id": state.get("task_id", ""),
        }

        # P0.1: 注入评测反馈（迭代循环时）
        eval_report = state.get("evaluation_report")
        if eval_report is not None:
            if isinstance(eval_report, dict):
                generation_input["evaluation_feedback"] = {
                    "issues": eval_report.get("critical_issues", []),
                    "recommendations": eval_report.get("recommendations", []),
                    "overall_score": float(eval_report.get("overall_score", 0.0)),
                }
            else:
                generation_input["evaluation_feedback"] = {
                    "issues": list(eval_report.critical_issues),
                    "recommendations": list(eval_report.recommendations),
                    "overall_score": float(eval_report.overall_score),
                }

        # Block F: 加载租户自定义 Prompt
        from app.core.logger import get_logger
        from app.orchestrator.state import TenantContext
        _log = get_logger("prd2tsd.generation_adapter")
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
                    agent_name="generation",
                    node_name="outline",
                    extra_vars={
                        "company_name": _settings.get("company_name", ""),
                        "industry": _settings.get("industry", ""),
                    },
                )
                if system_prompt:
                    generation_input["system_prompt"] = system_prompt
            except Exception as e:
                _log.warning("加载租户 Prompt 失败 (org=%s): %s", org_id, e)

        # Block F: Claims 检索 → 注入约束条件
        try:
            workspace_id = state.get("workspace_id", "")
            if workspace_id:
                from app.knowledge_layer.vector_store import PGVectorStore
                vs = PGVectorStore()
                planning_result = state.get("planning_result")
                query = (
                    str(planning_result.get("summary", ""))[:200]
                    if isinstance(planning_result, dict)
                    else ""
                )
                if query:
                    claim_results = await vs.search_claims(query=query, top_k=5)
                    if claim_results:
                        constraints = [c for c in claim_results if c.claim_type == "constraint"]
                        if constraints:
                            generation_input["claims_constraints"] = constraints[:3]
        except Exception as e:
            _log.warning("Claims 检索失败 (workspace=%s): %s", workspace_id, e)

        # 2. 调用 Generation Layer
        result = await self.graph.ainvoke(generation_input)

        # 3. 映射回 OrchestratorState
        state["generation_result"] = cast(GenerationResultDetail, result.get("generation_result"))
        state["section_contents"] = result.get("section_contents", {})
        state["export_formats"] = result.get("export_formats", {})
        state["progress"] = 0.75

        # Block F: 记录决策（供回放分析）
        if self.recorder is not None:
            await record_node_execution(
                self.recorder,
                state.get("task_id", ""),
                "generation",
                {"planning_ready": state.get("planning_result") is not None},
                str(state.get("prd_raw", ""))[:500],
                {
                    "generation_result": str(state.get("generation_result", ""))[:200],
                    "sections": len(state.get("section_contents", {})),
                },
            )

        return state
