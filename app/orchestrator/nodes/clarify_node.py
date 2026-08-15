"""clarify_node — 澄清节点（歧义输入 → 要求用户补充信息）。

当 IntentClassifier 判断用户输入歧义或信息不足时，
路由到此节点，设置状态为需要澄清。
"""

from __future__ import annotations

from app.core.logger import get_logger
from app.orchestrator.nodes.memory_context import get_event_bus
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator.clarify_node")


class ClarifyNode:
    """澄清节点 — 标记需要用户补充信息。

    不调用 LLM，仅设置 State 为澄清状态。
    调用方（API 路由）读取状态后提示用户补充信息。
    """

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """设置澄清状态。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新了 status / progress 的 OrchestratorState。
        """
        task_id = state.get("task_id", "")
        user_input = state.get("prd_raw", "")
        runtime = state.get("_runtime")

        logger.info("澄清节点: task=%s, input_preview=%.100s", task_id, user_input)

        # 推送澄清事件
        event_bus = getattr(runtime, "event_bus", None) if runtime else None
        if event_bus is None:
            # Runtime 未注入时回退全局 EventBus，保证 SSE 副作用真实生效
            event_bus = await get_event_bus()
        if event_bus is not None:
            from app.streaming.models import SseEvent
            await event_bus.publish(
                f"task:{task_id}",
                SseEvent(
                    type="chat.clarify",
                    payload={
                        "message": "您的输入不够明确，请提供更多信息。",
                        "hint": "请描述您想要完成的具体任务。",
                    },
                ),
            )

        state["status"] = "clarification_needed"
        state["progress"] = 1.0
        state["chat_response"] = "您的输入不够明确，请提供更多信息来描述您想要完成的具体任务。"

        return state
