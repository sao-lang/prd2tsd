"""retrieve_memory 节点 — 从历史会话中检索相关记忆。

接入已有的 MemoryRetriever，作为 LangGraph 图中的节点运行。
在每个新提问时自动检索相关历史记忆，注入到 State 供 LLM 使用。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator.retrieve_memory")


class RetrieveMemoryNode:
    """记忆检索节点 — 检索与当前查询相关的历史记忆。

    从 State 中提取当前查询和历史消息，调用 MemoryRetriever 检索，
    结果注入到 State 的 retrieved_memories 字段。
    """

    def __init__(self, memory_retriever: Any = None) -> None:
        """初始化记忆检索节点。

        Args:
            memory_retriever: MemoryRetriever 实例（可选，延迟注入）。
        """
        self._memory_retriever = memory_retriever

    def set_memory_retriever(self, retriever: Any) -> None:
        """注入 MemoryRetriever。

        Args:
            retriever: MemoryRetriever 实例。
        """
        self._memory_retriever = retriever

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行记忆检索。

        从 State 中提取用户查询和上下文消息，
        使用 MemoryRetriever 检索最相关的历史记忆。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新了 retrieved_memories 的 OrchestratorState。
        """
        task_id = state.get("task_id", "")
        user_query = state.get("prd_raw", "")

        if self._memory_retriever is None:
            logger.debug("MemoryRetriever 未注入，跳过记忆检索: task=%s", task_id)
            return state

        try:
            # 从 State 获取历史消息
            messages = state.get("_history_messages", [])  # type: ignore[typeddict-unknown-key]
            if not messages:
                logger.debug("无历史消息可用于检索: task=%s", task_id)
                return state

            # 检索
            results = await self._memory_retriever.retrieve(
                query=user_query[:500],
                messages=messages,
                strategy="hybrid",
                top_k=10,
            )

            # 写入 State
            state["retrieved_memories"] = [  # type: ignore[typeddict-unknown-key]
                {
                    "content": r.content,
                    "role": r.role,
                    "score": r.composite_score,
                }
                for r in results
            ]

            logger.info(
                "记忆检索完成: task=%s, retrieved=%d memories",
                task_id,
                len(results),
            )

        except Exception as exc:
            logger.warning("记忆检索失败（不中断流程）: task=%s, error=%s", task_id, exc)

        return state
