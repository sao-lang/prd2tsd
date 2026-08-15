"""retrieve_node — 知识查询节点（检索 + LLM 流式回答）。

替代原本 chat.py 路由处理器中手动检索→LLM 的方式，
作为 LangGraph 图节点运行，SSE 推送作为节点副作用。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.orchestrator.nodes.memory_context import build_memory_context, get_event_bus
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator.retrieve_node")


class KnowledgeQANode:
    """知识查询节点 — 知识检索 + LLM 流式回答。

    适用于：查文档、问概念、搜代码、技术问答。
    """

    def __init__(self, retrieval_pipeline: Any | None = None) -> None:
        """初始化知识查询节点。

        Args:
            retrieval_pipeline: RetrievalPipeline 实例（可选，未提供时自动创建）。
        """
        self._pipeline = retrieval_pipeline

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行知识检索 + LLM 流式回答。

        1. 调用 RetrievalPipeline 检索相关文档
        2. 构建带上下文的 Prompt
        3. 流式调用 LLM 生成回答
        4. 通过 EventBus 推送 SSE 事件

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新了 chat_response / status / progress 的 OrchestratorState。
        """
        user_input = state.get("prd_raw", "")
        task_id = state.get("task_id", "")
        workspace_id = state.get("workspace_id", "")
        runtime = state.get("_runtime")

        logger.info("KnowledgeQA 节点: task=%s, query_len=%d", task_id, len(user_input))

        # 获取 LLM Gateway
        llm_gateway = None
        if runtime is not None:
            llm_gateway = getattr(runtime, "llm_gateway", None)
        if llm_gateway is None:
            from app.llm_gateway import gateway as _gw
            llm_gateway = _gw

        event_bus = getattr(runtime, "event_bus", None) if runtime else None
        if event_bus is None:
            # Runtime 未注入时回退全局 EventBus，保证 SSE 副作用真实生效
            event_bus = await get_event_bus()

        # 记忆增强：注入历史相关记忆
        memory_context = await build_memory_context(state)

        # ── 阶段 1: 知识检索 ──
        if event_bus is not None:
            from app.streaming.models import SseEvent
            await event_bus.publish(
                f"task:{task_id}",
                SseEvent(
                    type="qna.status",
                    payload={"phase": "retrieving", "message": "正在检索知识图谱..."},
                ),
            )

        context = ""
        sources: list[dict[str, Any]] = []
        try:
            pipeline = self._pipeline
            if pipeline is None:
                from app.knowledge_layer.pipeline import RetrievalPipeline
                pipeline = RetrievalPipeline()

            retrieval_result = await pipeline.retrieve(
                query=user_input,
                workspace_id=workspace_id,
                top_k=5,
            )

            # 从 RetrievalContext 提取上下文
            context_parts: list[str] = []
            if hasattr(retrieval_result, "global_summary") and retrieval_result.global_summary:
                context_parts.append(str(retrieval_result.global_summary))
            for doc in retrieval_result.results[:5]:
                context_parts.append(doc.text)
            context = "\n---\n".join(context_parts)
            sources = [{"id": r.id, "score": r.score} for r in retrieval_result.results[:5]]

            if event_bus is not None:
                from app.streaming.models import SseEvent
                await event_bus.publish(
                    f"task:{task_id}",
                    SseEvent(
                        type="qna.status",
                        payload={
                            "phase": "retrieved",
                            "message": f"检索到 {len(sources)} 条相关结果",
                            "sources": sources,
                        },
                    ),
                )

        except Exception as exc:
            logger.warning("知识检索失败（降级直接回答）: task=%s, error=%s", task_id, exc)
            if event_bus is not None:
                from app.streaming.models import SseEvent
                await event_bus.publish(
                    f"task:{task_id}",
                    SseEvent(
                        type="qna.status",
                        payload={"phase": "retrieved", "message": "未找到知识库内容，将直接回答"},
                    ),
                )

        # ── 阶段 2: LLM 流式生成 ──
        if event_bus is not None:
            from app.streaming.models import SseEvent
            await event_bus.publish(
                f"task:{task_id}",
                SseEvent(
                    type="qna.status",
                    payload={"phase": "generating", "message": "正在生成回答..."},
                ),
            )

        # 构建带上下文的 Prompt（知识库 + 历史记忆）
        if context:
            prompt = (
                f"根据以下知识库内容回答用户问题。\n\n"
                f"知识库内容：\n{context}\n\n"
                f"用户问题：{user_input}\n\n"
                f"请基于知识库内容给出准确、专业的回答。如果知识库内容不足以回答问题，请说明。"
            )
            if memory_context:
                prompt = f"{memory_context}\n\n{prompt}"
        elif memory_context:
            prompt = f"{memory_context}\n\n用户问题：{user_input}"
        else:
            prompt = user_input

        try:
            full_response = ""
            async for token in llm_gateway.stream_complete(
                prompt=prompt,
                task_type="knowledge_qa",
                temperature=0.5,
                max_tokens=2048,
            ):
                full_response += token

                if event_bus is not None and len(token) > 0:
                    from app.streaming.models import SseEvent
                    await event_bus.publish(
                        f"task:{task_id}",
                        SseEvent(
                            type="qna.chunk",
                            payload={"content": token},
                        ),
                    )

        except Exception as exc:
            logger.error("KnowledgeQA LLM 调用失败: task=%s, error=%s", task_id, exc)
            full_response = f"抱歉，回答生成失败：{exc}"

        # 写入 State
        state["chat_response"] = full_response
        state["status"] = "complete"
        state["progress"] = 1.0

        # 推送完成事件
        if event_bus is not None:
            from app.streaming.models import SseEvent
            await event_bus.publish(
                f"task:{task_id}",
                SseEvent(
                    type="qna.done",
                    payload={
                        "content_length": len(full_response),
                        "sources": sources,
                    },
                ),
            )

        logger.info(
            "KnowledgeQA 节点完成: task=%s, response_len=%d, sources=%d",
            task_id,
            len(full_response),
            len(sources),
        )
        return state
