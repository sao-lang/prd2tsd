"""记忆上下文工具 — 历史消息加载 + 记忆检索，供 chat/retrieve/retrieve_memory 节点复用。"""

from __future__ import annotations

from typing import Any

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.orchestrator.state import OrchestratorState
from app.session_history.memory_retriever import MemoryRetriever
from app.session_history.repository import SessionRepository

logger = get_logger("prd2tsd.orchestrator.memory_context")


async def load_history_messages(state: OrchestratorState) -> list[dict[str, str]]:
    """加载历史会话消息。

    优先使用 State 中已注入的 _history_messages；为空且存在 session_id 时，
    从 sessions 表读取最近 50 条消息作为历史记忆输入。

    Args:
        state: 当前 OrchestratorState。

    Returns:
        历史消息列表 [{"role", "content", "timestamp"}...]。
    """
    messages = state.get("_history_messages", [])
    if messages:
        return messages

    session_id = state.get("session_id", "")
    if not session_id:
        return []

    try:
        pg_connector = connection_manager.get("postgres")
        async with pg_connector.get_session() as db:  # type: ignore[attr-defined]
            page = await SessionRepository().get_messages(db, session_id, page=1, page_size=50)
            loaded = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": (msg.created_at or ""),
                }
                for msg in page.items
            ]
        # 回写 State，避免重复查库
        state["_history_messages"] = loaded
        logger.info("从会话加载历史消息: session=%s, count=%d", session_id, len(loaded))
        return loaded
    except Exception as exc:
        logger.warning("加载历史消息失败（降级为空）: session=%s, error=%s", session_id, exc)
        return []


async def build_memory_context(state: OrchestratorState) -> str:
    """构建记忆上下文文本并写入 retrieved_memories。

    用 MemoryRetriever 对历史消息做 hybrid 检索，返回可注入 prompt 的文本；
    检索结果同时写入 State.retrieved_memories 供上层持久化/调试。

    Args:
        state: 当前 OrchestratorState。

    Returns:
        记忆上下文文本（无记忆时为空字符串）。
    """
    user_query = state.get("prd_raw", "")
    messages = await load_history_messages(state)
    if not messages or not user_query:
        state["retrieved_memories"] = []
        return ""

    try:
        retriever = MemoryRetriever()
        results = await retriever.retrieve(
            query=user_query[:500],
            messages=messages,
            strategy="hybrid",
            top_k=8,
        )
        state["retrieved_memories"] = [
            {
                "content": r.content,
                "role": r.role,
                "score": r.composite_score,
            }
            for r in results
        ]
        if not results:
            return ""
        parts = "\n".join(f"- [{r.role}] {r.content[:300]}" for r in results)
        return f"以下是该会话中与当前问题相关的历史记忆，供回答时参考：\n{parts}"
    except Exception as exc:
        logger.warning("记忆检索失败（降级无记忆）: error=%s", exc)
        state["retrieved_memories"] = []
        return ""


async def get_event_bus() -> Any:
    """获取事件总线（全局单例，供节点副作用推送 SSE）。"""
    from app.streaming import event_bus as _bus

    return _bus
