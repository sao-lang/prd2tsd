"""Runtime 注入中间件 — 每次请求重建 Runtime 上下文。

Runtime 对象（含 DB 会话、EventBus、LLM Gateway）不写入 checkpoint，
每次恢复/新请求时重新注入到 State 中供当前节点使用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.logger import get_logger
from app.orchestrator.state import OrchestratorRuntime, OrchestratorState

logger = get_logger("prd2tsd.orchestrator.runtime")


class RuntimeInjector:
    """Runtime 注入器 — 在每个节点执行前注入运行时上下文。

    通过 LangGraph 的 per-node 中间件机制工作。
    从外部工厂函数重建 Runtime（新 DB 会话、新 EventBus 引用），
    注入到 State 的 _runtime 字段，仅当前节点可见，不进 checkpoint。
    """

    def __init__(self, runtime_factory: Any = None) -> None:
        """初始化 Runtime 注入器。

        Args:
            runtime_factory: 可调用对象，签名为 (thread_id, user_id) -> OrchestratorRuntime。
        """
        self._runtime_factory = runtime_factory

    def set_runtime_factory(self, factory: Any) -> None:
        """设置 Runtime 工厂函数。

        Args:
            factory: 可调用对象，签名为 (thread_id, user_id) -> OrchestratorRuntime。
        """
        self._runtime_factory = factory

    async def inject(self, state: OrchestratorState) -> OrchestratorState:
        """注入 Runtime 到 State。

        从 config 中提取 thread_id / user_id，重建 Runtime 上下文。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            注入了 _runtime 字段的 OrchestratorState。
        """
        thread_id = state.get("task_id", "")
        user_id = state.get("user_id", "")

        if self._runtime_factory is not None:
            runtime = await self._runtime_factory(thread_id, user_id)
        else:
            runtime = OrchestratorRuntime(
                current_user_id=user_id,
                current_workspace_id=state.get("workspace_id", ""),
            )

        state["_runtime"] = runtime  # type: ignore[typeddict-unknown-key]
        return state

    @staticmethod
    def make_default_runtime(
        user_id: str = "",
        workspace_id: str = "",
        db_session: Any = None,
        event_bus: Any = None,
        llm_gateway: Any = None,
    ) -> OrchestratorRuntime:
        """创建默认 Runtime 实例。

        Args:
            user_id: 用户 ID。
            workspace_id: 工作空间 ID。
            db_session: 数据库会话。
            event_bus: 事件总线。
            llm_gateway: LLM Gateway。

        Returns:
            OrchestratorRuntime 实例。
        """
        return OrchestratorRuntime(
            db_session=db_session,
            event_bus=event_bus,
            llm_gateway=llm_gateway,
            current_user_id=user_id,
            current_workspace_id=workspace_id,
        )
