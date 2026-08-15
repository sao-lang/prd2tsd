"""chat_node — 纯对话 LLM 节点（闲聊/问候/普通交流）。

替代原本 chat.py 路由处理器中手动调 LLM 的方式，
作为 LangGraph 图节点运行，SSE 推送作为节点副作用。
"""

from __future__ import annotations

from app.core.logger import get_logger
from app.orchestrator.nodes.memory_context import build_memory_context, get_event_bus
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator.chat_node")


class ChatNode:
    """纯对话节点 — 直接调用 LLM 回答问题。

    不涉及知识检索，不涉及复杂生成管线。
    适用于：闲聊、问候、简单问答。
    """

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行纯对话 LLM 调用。

        从 State 读取用户输入（prd_raw），调用 LLM Gateway，
        将回复写入 chat_response 字段，并通过 EventBus 推送 SSE 事件。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新了 chat_response / status / progress 的 OrchestratorState。
        """
        user_input = state.get("prd_raw", "")
        task_id = state.get("task_id", "")
        runtime = state.get("_runtime")

        logger.info("Chat 节点: task=%s, input_len=%d", task_id, len(user_input))

        # 获取 LLM Gateway（优先从 Runtime，其次全局）
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

        # 推送开始事件
        if event_bus is not None:
            from app.streaming.models import SseEvent
            await event_bus.publish(
                f"task:{task_id}",
                SseEvent(
                    type="chat.status",
                    payload={"phase": "generating", "message": "正在生成回答..."},
                ),
            )

        try:
            # 流式调用 LLM（带记忆上下文）
            prompt = f"{memory_context}\n\n用户问题：{user_input}" if memory_context else user_input
            full_response = ""
            async for token in llm_gateway.stream_complete(
                prompt=prompt,
                task_type="chat",
                temperature=0.7,
                max_tokens=1024,
            ):
                full_response += token

                # 每积累 50 字符推送一次 chunk
                if event_bus is not None and len(token) > 0:
                    from app.streaming.models import SseEvent
                    await event_bus.publish(
                        f"task:{task_id}",
                        SseEvent(
                            type="chat.chunk",
                            payload={"content": token},
                        ),
                    )

        except Exception as exc:
            logger.error("Chat LLM 调用失败: task=%s, error=%s", task_id, exc)
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
                    type="chat.done",
                    payload={"content_length": len(full_response)},
                ),
            )

        logger.info("Chat 节点完成: task=%s, response_len=%d", task_id, len(full_response))
        return state
