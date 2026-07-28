"""块 D — 主编排 StateGraph。

串联 4 个 Agent Layer（Analysis → Planning → Generation → Evaluation）
+ 知识检索 + 迭代决策 + Human-in-the-Loop。

通过 PostgreSQL Checkpointer 实现断点持久化恢复。
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from app.core.config import Settings
from app.core.logger import get_logger
from app.knowledge_layer.pipeline import RetrievalPipeline
from app.observability.replay.recorder import DecisionRecorder
from app.orchestrator.adapters import (
    AnalysisAdapter,
    EvaluationAdapter,
    GenerationAdapter,
    PlanningAdapter,
)
from app.orchestrator.human_review import HumanReviewNode
from app.orchestrator.iteration import IterationDecider
from app.orchestrator.routing import needs_review
from app.orchestrator.state import OrchestratorConfig, OrchestratorState

logger = get_logger("prd2tsd.orchestrator")


class KnowledgeRetrievalNode:
    """知识检索节点 — 调用块 B 的 RetrievalPipeline。"""

    def __init__(self, pipeline: RetrievalPipeline) -> None:
        """初始化知识检索节点。

        Args:
            pipeline: RetrievalPipeline 实例。
        """
        self.pipeline = pipeline
        # Block F: 决策记录器
        self.recorder = DecisionRecorder()

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行知识检索。

        Block F: 集成 DecisionRecorder 记录决策。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新后的 OrchestratorState。
        """
        task_id = state.get("task_id", "")
        logger.info("知识检索开始: task=%s", task_id)
        prd_raw = state.get("prd_raw", "")
        workspace_id = state.get("workspace_id", "")

        # Block F: 开始决策追踪
        await self.recorder.start_trace(task_id)

        if not prd_raw.strip():
            logger.warning("PRD 内容为空，跳过知识检索")
            state["knowledge_context"] = None
            state["progress"] = 0.10
            return state

        try:
            ctx = await self.pipeline.retrieve(
                query=prd_raw[:500],
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
    Block F 增强：结束决策追踪。
    """

    def __init__(self) -> None:
        self.recorder = DecisionRecorder()

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """组装最终结果。

        Block F: 结束 DecisionRecorder 追踪。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            完成状态的 OrchestratorState。
        """
        task_id = state.get("task_id", "")
        logger.info("最终组装: task=%s", task_id)
        state["status"] = "complete"
        state["progress"] = 1.0

        # Block F: 结束决策追踪
        await self.recorder.end_trace(task_id)

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
    session_service: Any = None,
    context_compressor: Any = None,
    memory_retriever: Any = None,
) -> StateGraph:
    """构建主编排 StateGraph。

    Phase 2 增强：接入 save_session / compress_memory / retrieve_memory 节点。

    Args:
        analysis_graph: 编译后的 Analysis Layer StateGraph。
        planning_graph: 编译后的 Planning Layer StateGraph。
        generation_graph: 编译后的 Generation Layer StateGraph。
        evaluation_graph: 编译后的 Evaluation Layer StateGraph。
        retrieval_pipeline: RetrievalPipeline 实例（可选）。
        session_service: SessionHistoryService 实例（可选，用于持久化）。
        context_compressor: ContextCompressor 实例（可选，用于记忆压缩）。
        memory_retriever: MemoryRetriever 实例（可选，用于记忆检索）。

    Returns:
        主编排 StateGraph（未编译）。
    """
    from app.orchestrator.nodes.compress_memory import CompressMemoryNode
    from app.orchestrator.nodes.retrieve_memory import RetrieveMemoryNode
    from app.orchestrator.nodes.save_session import SaveSessionNode

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

    # Phase 2-3: 记忆管理节点
    compress_memory_node = CompressMemoryNode(compressor=context_compressor)
    save_session_node = SaveSessionNode(session_service=session_service)
    retrieve_memory_node = RetrieveMemoryNode(memory_retriever=memory_retriever)

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

    # Phase 2-3: 记忆管理节点
    graph.add_node("retrieve_memory", retrieve_memory_node.run)
    graph.add_node("compress_memory", compress_memory_node.run)
    graph.add_node("save_session", save_session_node.run)

    # 连线：入口 → 记忆检索 → 知识检索 → 分析
    graph.set_entry_point("retrieve_memory")
    graph.add_edge("retrieve_memory", "knowledge_retrieval")
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

    # Phase 2-3: 最终组装 → 记忆压缩 → 会话保存 → 结束
    graph.add_edge("final_assembly", "compress_memory")
    graph.add_edge("compress_memory", "save_session")
    graph.add_edge("save_session", END)

    return graph


# ── 便捷函数 ──


def build_and_compile(
    analysis_graph: StateGraph,
    planning_graph: StateGraph,
    generation_graph: StateGraph,
    evaluation_graph: StateGraph,
    retrieval_pipeline: RetrievalPipeline | None = None,
    use_checkpointer: bool = False,
    checkpointer: BaseCheckpointSaver | None = None,
    config: OrchestratorConfig | None = None,
    session_service: Any = None,
    context_compressor: Any = None,
    memory_retriever: Any = None,
) -> StateGraph:
    """构建并编译主编排 StateGraph。

    支持 MemorySaver（开发）和 PostgresSaver（生产）两种 checkpointer。

    Args:
        analysis_graph: 编译后的 Analysis Layer StateGraph。
        planning_graph: 编译后的 Planning Layer StateGraph。
        generation_graph: 编译后的 Generation Layer StateGraph。
        evaluation_graph: 编译后的 Evaluation Layer StateGraph。
        retrieval_pipeline: RetrievalPipeline 实例（可选）。
        use_checkpointer: 是否启用 checkpointer（用于 interrupt/resume）。
        checkpointer: 外部注入的 checkpointer 实例（优先级高于 use_checkpointer）。
        config: OrchestratorConfig 静态配置（可选）。
        session_service: SessionHistoryService 实例（可选）。
        context_compressor: ContextCompressor 实例（可选）。
        memory_retriever: MemoryRetriever 实例（可选）。

    Returns:
        编译后的主编排 StateGraph。
    """
    graph = build_orchestrator_graph(
        analysis_graph=analysis_graph,
        planning_graph=planning_graph,
        generation_graph=generation_graph,
        evaluation_graph=evaluation_graph,
        retrieval_pipeline=retrieval_pipeline,
        session_service=session_service,
        context_compressor=context_compressor,
        memory_retriever=memory_retriever,
    )

    effective_checkpointer: BaseCheckpointSaver | None = None
    if checkpointer is not None:
        effective_checkpointer = checkpointer
    elif use_checkpointer:
        from langgraph.checkpoint.memory import MemorySaver
        effective_checkpointer = MemorySaver()

    if effective_checkpointer is not None:
        return graph.compile(checkpointer=effective_checkpointer)
    return graph.compile()


async def create_postgres_checkpointer(
    db_url: str | None = None,
) -> BaseCheckpointSaver:
    """创建 PostgreSQL checkpointer 并自动建表。

    用于生产环境的断点持久化恢复。

    Args:
        db_url: PostgreSQL 连接字符串，默认从 Settings 读取。

    Returns:
        已初始化（建表完成）的 PostgresSaver 实例。
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    if db_url is None:
        db_url = Settings().DATABASE_URL

    # PostgresSaver 需要 sync 连接字符串（不含 +asyncpg）
    sync_url = db_url.replace("+asyncpg", "")
    checkpointer = PostgresSaver.from_conn_string(sync_url)
    await checkpointer.setup()
    logger.info("PostgreSQL checkpointer 已初始化")
    return checkpointer


async def create_memory_checkpointer() -> BaseCheckpointSaver:
    """创建内存 checkpointer（开发/测试用）。

    Returns:
        MemorySaver 实例。
    """
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()
