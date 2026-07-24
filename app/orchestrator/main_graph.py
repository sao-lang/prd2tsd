"""块 D — 主编排 StateGraph。

串联 4 个 Agent Layer（Analysis → Planning → Generation → Evaluation）
+ 知识检索 + 迭代决策 + Human-in-the-Loop。
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.core.logger import get_logger
from app.knowledge_layer.pipeline import RetrievalPipeline
from app.orchestrator.adapters import (
    AnalysisAdapter,
    EvaluationAdapter,
    GenerationAdapter,
    PlanningAdapter,
)
from app.orchestrator.human_review import HumanReviewNode
from app.orchestrator.iteration import IterationDecider
from app.orchestrator.routing import needs_review
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator")


class KnowledgeRetrievalNode:
    """知识检索节点 — 调用块 B 的 RetrievalPipeline。"""

    def __init__(self, pipeline: RetrievalPipeline) -> None:
        """初始化知识检索节点。

        Args:
            pipeline: RetrievalPipeline 实例。
        """
        self.pipeline = pipeline

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行知识检索。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        logger.info("知识检索开始: task=%s", state.get("task_id"))
        prd_raw = state.get("prd_raw", "")
        workspace_id = state.get("workspace_id", "")

        if not prd_raw.strip():
            logger.warning("PRD 内容为空，跳过知识检索")
            state["knowledge_context"] = None
            state["progress"] = 0.10
            return state

        try:
            ctx = await self.pipeline.retrieve(
                query=prd_raw[:500],  # 用 PRD 前 500 字做检索
                mode="hybrid",
                top_k=10,
                workspace_id=workspace_id,
            )
            state["knowledge_context"] = ctx
            logger.info("知识检索完成: docs=%d", len(ctx.results))
        except Exception as exc:
            logger.warning("知识检索失败（降级继续）: %s", exc)
            state["knowledge_context"] = None

        state["progress"] = 0.10
        return state


class FinalAssemblyNode:
    """最终组装节点 — 汇总所有层输出为最终结果。

    E5 增强：任务完成后自动触发 Webhook 通知。
    """

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """组装最终结果。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            完成状态的 OrchestratorState。
        """
        logger.info("最终组装: task=%s", state.get("task_id"))
        state["status"] = "complete"
        state["progress"] = 1.0

        # E5 增强：任务完成后触发 Webhook 通知
        try:
            from app.integrations.webhook import WebhookSender, integration_hub
            workspace_id = state.get("workspace_id", "")
            task_id = state.get("task_id", "")
            if workspace_id and task_id:
                await integration_hub.notify(
                    event="task.completed",
                    payload={
                        "task_id": task_id,
                        "workspace_id": workspace_id,
                        "status": "completed",
                        "progress": 1.0,
                    },
                    sender=WebhookSender(),
                )
                logger.info("Webhook 通知已发送: task=%s", task_id)
        except Exception as exc:
            logger.warning("Webhook 通知发送失败（不影响主流程）: %s", exc)

        return state


def build_orchestrator_graph(
    analysis_graph: StateGraph,
    planning_graph: StateGraph,
    generation_graph: StateGraph,
    evaluation_graph: StateGraph,
    retrieval_pipeline: RetrievalPipeline | None = None,
) -> StateGraph:
    """构建主编排 StateGraph。

    Args:
        analysis_graph: 编译后的 Analysis Layer StateGraph。
        planning_graph: 编译后的 Planning Layer StateGraph。
        generation_graph: 编译后的 Generation Layer StateGraph。
        evaluation_graph: 编译后的 Evaluation Layer StateGraph。
        retrieval_pipeline: RetrievalPipeline 实例（可选）。

    Returns:
        编译后的主编排 StateGraph。
    """
    pipeline = retrieval_pipeline or RetrievalPipeline()

    # 创建节点
    kn_node = KnowledgeRetrievalNode(pipeline)
    analysis_adapter = AnalysisAdapter(analysis_graph)
    analysis_review = HumanReviewNode("analysis")
    planning_adapter = PlanningAdapter(planning_graph)
    planning_review = HumanReviewNode("planning")
    generation_adapter = GenerationAdapter(generation_graph)
    evaluation_adapter = EvaluationAdapter(evaluation_graph)
    iteration_decider = IterationDecider()
    final_assembly = FinalAssemblyNode()

    # 构建图
    graph = StateGraph(OrchestratorState)

    graph.add_node("knowledge_retrieval", kn_node.run)
    graph.add_node("analysis", analysis_adapter.run)
    graph.add_node("analysis_human_review", analysis_review.run)
    graph.add_node("planning", planning_adapter.run)
    graph.add_node("planning_human_review", planning_review.run)
    graph.add_node("generation", generation_adapter.run)
    graph.add_node("evaluation", evaluation_adapter.run)
    graph.add_node("final_assembly", final_assembly.run)

    # 连线：入口 → 知识检索 → 分析
    graph.set_entry_point("knowledge_retrieval")
    graph.add_edge("knowledge_retrieval", "analysis")

    # 分析 → 条件路由（是否需要人工审核）
    graph.add_conditional_edges(
        "analysis",
        needs_review,
        {
            "review_needed": "analysis_human_review",
            "skip_review": "planning",
        },
    )
    graph.add_edge("analysis_human_review", "planning")

    # 规划 → 条件路由（是否需要人工审核）
    graph.add_conditional_edges(
        "planning",
        needs_review,
        {
            "review_needed": "planning_human_review",
            "skip_review": "generation",
        },
    )
    graph.add_edge("planning_human_review", "generation")

    # 生成 → 评测
    graph.add_edge("generation", "evaluation")

    # 评测 → 迭代决策（条件路由）
    graph.add_conditional_edges(
        "evaluation",
        iteration_decider.run,
        {
            "final_assembly": "final_assembly",
            "planning": "planning",
            "generation": "generation",
            "analysis_human_review": "analysis_human_review",
        },
    )

    # 最终组装 → 结束
    graph.add_edge("final_assembly", END)

    return graph


# ── 便捷函数 ──


def build_and_compile(
    analysis_graph: StateGraph,
    planning_graph: StateGraph,
    generation_graph: StateGraph,
    evaluation_graph: StateGraph,
    retrieval_pipeline: RetrievalPipeline | None = None,
    use_checkpointer: bool = False,
) -> StateGraph:
    """构建并编译主编排 StateGraph。

    Args:
        analysis_graph: 编译后的 Analysis Layer StateGraph。
        planning_graph: 编译后的 Planning Layer StateGraph。
        generation_graph: 编译后的 Generation Layer StateGraph。
        evaluation_graph: 编译后的 Evaluation Layer StateGraph。
        retrieval_pipeline: RetrievalPipeline 实例（可选）。
        use_checkpointer: 是否启用 MemorySaver checkpointer（用于 interrupt/resume）。

    Returns:
        编译后的主编排 StateGraph。
    """
    from langgraph.checkpoint.memory import MemorySaver

    graph = build_orchestrator_graph(
        analysis_graph=analysis_graph,
        planning_graph=planning_graph,
        generation_graph=generation_graph,
        evaluation_graph=evaluation_graph,
        retrieval_pipeline=retrieval_pipeline,
    )

    if use_checkpointer:
        return graph.compile(checkpointer=MemorySaver())
    return graph.compile()
