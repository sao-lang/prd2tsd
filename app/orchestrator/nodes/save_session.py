"""save_session 节点 — 将任务结果持久化到 sessions / messages 表。

替代原本 TaskManager._update_result() 的内存 dict 写入方式，
改为写入 PostgreSQL，支持完整的会话历史记录。
"""

from __future__ import annotations

from typing import Any

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

        # 从 Runtime 获取 DB 会话
        runtime = state.get("_runtime")  # type: ignore[typeddict-unknown-key]
        db_session = getattr(runtime, "db_session", None) if runtime else None

        if db_session is None:
            logger.warning("无 DB 会话可用，跳过会话持久化: task=%s", task_id)
            return state

        if self._session_service is None:
            logger.warning("SessionHistoryService 未注入，跳过会话持久化: task=%s", task_id)
            return state

        try:
            # 提取结果摘要
            generation_result = state.get("generation_result")
            evaluation_report = state.get("evaluation_report")

            result_summary = ""
            if generation_result is not None:
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

            # 记录任务完成事件（通过 EventBus）
            event_bus = getattr(runtime, "event_bus", None) if runtime else None
            if event_bus is not None:
                from app.streaming.models import SseEvent

                await event_bus.publish(
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

            logger.info(
                "会话已保存: task=%s, status=%s, score=%s",
                task_id,
                status,
                overall_score,
            )

        except Exception as exc:
            logger.warning("会话保存失败（不影响主流程）: task=%s, error=%s", task_id, exc)

        return state
