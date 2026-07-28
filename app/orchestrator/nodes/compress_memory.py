"""compress_memory 节点 — Token 超限时自动压缩会话记忆。

接入已有的 ContextCompressor，作为 LangGraph 图中的节点运行。
在会话保存之前执行，确保后续 LLM 调用不会因上下文过长而失败。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator.compress_memory")


class CompressMemoryNode:
    """记忆压缩节点 — 对过长上下文进行摘要压缩。

    从 State 中提取历史消息，调用 ContextCompressor 压缩后，
    将压缩结果注入到 State 的 compressed_context 字段。
    """

    def __init__(self, compressor: Any = None) -> None:
        """初始化记忆压缩节点。

        Args:
            compressor: ContextCompressor 实例（可选，延迟注入）。
        """
        self._compressor = compressor

    def set_compressor(self, compressor: Any) -> None:
        """注入 ContextCompressor。

        Args:
            compressor: ContextCompressor 实例。
        """
        self._compressor = compressor

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """执行记忆压缩。

        从 State 中读取历史消息列表，判断是否需要压缩，
        如需要则通过 ContextCompressor 执行压缩。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            更新了 compressed_context 的 OrchestratorState。
        """
        task_id = state.get("task_id", "")

        if self._compressor is None:
            logger.debug("ContextCompressor 未注入，跳过记忆压缩: task=%s", task_id)
            return state

        try:
            # 从 State 获取历史消息
            messages = state.get("_history_messages", [])  # type: ignore[typeddict-unknown-key]

            if not messages:
                logger.debug("无历史消息需要压缩: task=%s", task_id)
                return state

            # 将 dict 消息转为 ChatMessage
            from app.session_history.compressor import ChatMessage

            chat_messages: list[Any] = [
                ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
                for m in messages
            ]

            # 执行压缩
            compressed = await self._compressor.compress(chat_messages)

            # 写入 State
            state["compressed_context"] = [  # type: ignore[typeddict-unknown-key]
                {"role": m.role, "content": m.content} for m in compressed
            ]

            logger.info(
                "记忆压缩完成: task=%s, %d→%d messages",
                task_id,
                len(messages),
                len(compressed),
            )

        except Exception as exc:
            logger.warning("记忆压缩失败（不中断流程）: task=%s, error=%s", task_id, exc)

        return state
