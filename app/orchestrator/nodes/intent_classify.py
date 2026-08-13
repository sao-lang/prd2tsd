"""intent_classify 节点 — 意图分类 LangGraph 节点。

将原本在 chat.py 路由处理器中手动调用的 IntentClassifier 包装为 LangGraph 节点，
配合 add_conditional_edges 实现意图驱动的路由分发。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.orchestrator.intent_classifier import IntentClassifier, IntentResult
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator.intent_classify")

# 意图 → 路由目标映射
INTENT_ROUTE_MAP: dict[str, str] = {
    "chat": "chat_node",
    "knowledge_qa": "retrieve_node",
    "complex_generation": "kg_retrieve",
    "clarification": "clarify_node",
}


class IntentClassifyNode:
    """意图分类节点 — 判断用户输入类型并写入 State。

    分类结果存储在 state["intent"] 中，供后续条件路由使用。
    """

    def __init__(self, classifier: IntentClassifier | None = None, llm_gateway: Any = None) -> None:
        """初始化意图分类节点。

        Args:
            classifier: IntentClassifier 实例（可选，未提供则自动创建）。
            llm_gateway: LLM Gateway 实例（可选）。
        """
        self._classifier = classifier or IntentClassifier(llm_gateway=llm_gateway)

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行意图分类。

        幂等：state 已含 intent 时跳过分类。
        统一交互入口（/interact）已在路由层分类并预写入 state，
        此处检测到 intent 后直接复用，避免"双实现"重复分类。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新了 intent 字段的 OrchestratorState。
        """
        # 幂等：state 已含 intent 则跳过分类
        if state.get("intent"):
            logger.info("意图已存在，跳过分类: %s", state["intent"])
            return state

        user_input = state.get("prd_raw", "")

        # 分类
        result: IntentResult = await self._classifier.classify(user_input)

        # 写入 State
        state["intent"] = result.intent.value
        state["intent_confidence"] = result.confidence
        state["intent_sub"] = result.sub_intent

        logger.info(
            "意图分类: intent=%s, confidence=%.2f, sub=%s",
            result.intent.value,
            result.confidence,
            result.sub_intent,
        )

        return state


def route_by_intent(state: OrchestratorState) -> str:
    """根据 State 中的 intent 字段决定路由目标。

    用于 LangGraph add_conditional_edges 的条件路由函数。

    Args:
        state: 当前 OrchestratorState。

    Returns:
        路由目标节点名。
    """
    intent = state.get("intent", "chat")
    return INTENT_ROUTE_MAP.get(intent, "chat_node")
