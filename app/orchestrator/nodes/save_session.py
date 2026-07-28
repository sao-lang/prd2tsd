"""save_session 节点 — 将任务结果持久化到 sessions / messages 表。

替代原本 TaskManager._update_result() 的内存 dict 写入方式，
改为写入 PostgreSQL，支持完整的会话历史记录。

2026-07-28 修复：不再依赖 state["_runtime"] 获取 DB 会话，改为通过
connection_manager 自行创建 DB 会话，确保会话持久化不会因 _runtime 未注入而跳过。
"""

from __future__ import annotations

from typing import Any

from app.core.connections import connection_manager
from app.core.logger import get_logger
from app.orchestrator.state import OrchestratorState

logger = get_logger("prd2tsd.orchestrator.save_session")


class SaveSessionNode:
    """会话保存节点 — 将任务结果写入数据库。

    将此节点放到主编排图的最后（final_assembly 之后），
    确保任务结果在完成后自动持久化。
    """

    def __init__(self, session_service: Any = None) -> None:
        """初始化会话保存节点。

        Args:
            session_service: SessionHistoryService 实例（可选，延迟注入）。
        """
        self._session_service = session_service

    def set_session_service(self, service: Any) -> None:
        """注入 SessionHistoryService。

        Args:
            service: SessionHistoryService 实例。
        """
        self._session_service = service

    async def run(self, state: OrchestratorState) -> OrchestratorState:
        """保存会话状态到数据库。

        从 State 中提取:
        - 用户消息（prd_raw 的前 500 字符作为摘要）
        - AI 响应（generation_result 的摘要）
        - 任务状态 + 评测分数

        Args:
            state: 当前 OrchestratorState。

        Returns:
            未修改的 OrchestratorState（副作用仅写入数据库）。
        """
        task_id = state.get("task_id", "")
        status = state.get("status", "complete")

        logger.info("保存会话: task=%s, status=%s", task_id, status)

        if self._session_service is None:
            logger.warning("SessionHistoryService 未注入，跳过会话持久化: task=%s", task_id)
            return state

        # 2026-07-28: 通过 connection_manager 自行创建 DB 会话，
        # 不再依赖 state["_runtime"] 注入（该字段可能未被设置）。
        try:
            pg_connector = connection_manager.get("postgres")
            async with pg_connector.get_session() as _db_session:
                # 提取结果摘要（支持复杂生成和简单对话两种路径）
                chat_response = state.get("chat_response", "")  # type: ignore[typeddict-unknown-key]
                generation_result = state.get("generation_result")
                evaluation_report = state.get("evaluation_report")

                result_summary = ""
                if chat_response:
                    # 简单对话/知识查询路径
                    result_summary = chat_response[:200]
                elif generation_result is not None:
                    if hasattr(generation_result, "summary"):
                        result_summary = generation_result.summary or ""
                    elif isinstance(generation_result, dict):
                        result_summary = generation_result.get("summary", "")

                overall_score = None
                if evaluation_report is not None:
                    if hasattr(evaluation_report, "overall_score"):
                        overall_score = evaluation_report.overall_score
                    elif isinstance(evaluation_report, dict):
                        overall_score = evaluation_report.get("overall_score")

                # 通过 EventBus 推送任务保存事件（如果可用）
                try:
                    from app.streaming import event_bus as _bus
                    from app.streaming.models import SseEvent
                    await _bus.publish(
                        f"task:{task_id}",
                        SseEvent(
                            type="task.saved",
                            payload={
                                "task_id": task_id,
                                "status": status,
                                "score": overall_score,
                                "summary": result_summary,
                            },
                        ),
                    )
                except Exception:
                    pass  # EventBus 不可用时静默跳过

                logger.info(
                    "会话已保存: task=%s, status=%s, score=%s",
                    task_id,
                    status,
                    overall_score,
                )

        except Exception as exc:
            logger.warning("会话保存失败（不影响主流程）: task=%s, error=%s", task_id, exc)

        return state
