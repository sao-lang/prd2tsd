"""Runtime 注入中间件 — 每次请求重建 Runtime 上下文。

Runtime 对象（含 DB 会话、EventBus、LLM Gateway）不写入 checkpoint，
每次恢复/新请求时重新注入到 State 中供当前节点使用。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger
from app.orchestrator.state import OrchestratorRuntime, OrchestratorState

logger = get_logger("prd2tsd.orchestrator.runtime")

# 线程级运行时注册表：thread_id → OrchestratorRuntime
_runtime_registry: dict[str, OrchestratorRuntime] = {}


def register_runtime(thread_id: str, runtime: OrchestratorRuntime) -> None:
    """注册线程运行时。"""
    _runtime_registry[thread_id] = runtime


def get_registered_runtime(thread_id: str) -> OrchestratorRuntime | None:
    """获取线程运行时；未注册返回 None。"""
    return _runtime_registry.get(thread_id)


def unregister_runtime(thread_id: str) -> None:
    """注销线程运行时。"""
    _runtime_registry.pop(thread_id, None)



class RuntimeInjector:
    """Runtime 注入器 — 入口节点为 thread_id 注册运行时上下文。

    Runtime（DB 会话 / EventBus / LLM Gateway）不可被 checkpoint 序列化，
    因此通过线程级注册表按 thread_id 注入：入口节点注册、消费节点读取、
    任务结束（save_session / clarify 节点）注销。
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
        """为 thread_id 注册 Runtime 上下文。

        从 state 提取 thread_id / user_id，重建 Runtime 并写入线程级注册表；
        不修改 State，避免不可序列化对象进入 checkpoint。

        Args:
            state: 当前 OrchestratorState。

        Returns:
            原样返回的 OrchestratorState。
        """
        thread_id = state.get("task_id", "")
        user_id = state.get("user_id", "")

        if self._runtime_factory is not None:
            runtime = await self._runtime_factory(thread_id, user_id)
        else:
            # 默认注入全局 EventBus / LLM Gateway；节点内仍有兜底，双保险
            gateway: Any = None
            event_bus: Any = None
            try:
                from app.llm_gateway import gateway
                from app.streaming import event_bus
            except Exception:
                gateway = None
                event_bus = None
            runtime = OrchestratorRuntime(
                db_session=None,
                event_bus=event_bus,
                llm_gateway=gateway,
                current_user_id=user_id,
                current_workspace_id=state.get("workspace_id", ""),
            )

        register_runtime(thread_id, runtime)
        return state
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
