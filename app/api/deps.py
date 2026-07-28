"""全局依赖注入。"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.core.connections import connection_manager
from app.llm_gateway import config_manager, gateway
from app.orchestrator.main_graph import build_and_compile
from app.security.audit_logger import audit_logger
from app.security.data_masking import DataMaskingEngine

# 缓存编译后的 Orchestrator 和 DataMaskingEngine（懒加载）
_orchestrator_instance = None
_masking_engine_instance = None
_checkpointer_instance: BaseCheckpointSaver | None = None


def set_checkpointer(checkpointer: BaseCheckpointSaver) -> None:
    """注入 Checkpointer 实例（在 lifespan 中调用）。

    Args:
        checkpointer: LangGraph checkpointer 实例（PostgresSaver 或 MemorySaver）。
    """
    global _checkpointer_instance
    _checkpointer_instance = checkpointer


async def get_db_session():
    """获取数据库会话。

    Yields:
        AsyncSession。
    """
    connector = connection_manager.get("postgres")
    async with connector.get_session() as session:
        yield session


def get_gateway():
    """获取 LLM Gateway 实例。

    Returns:
        LLMGateway 实例。
    """
    return gateway


def get_config_manager():
    """获取模型配置管理器。

    Returns:
        ModelConfigManager 实例。
    """
    return config_manager


def get_masking_engine():
    """获取数据脱敏引擎（单例缓存）。

    Returns:
        DataMaskingEngine 实例。
    """
    global _masking_engine_instance
    if _masking_engine_instance is None:
        _masking_engine_instance = DataMaskingEngine()
    return _masking_engine_instance


def get_audit_logger():
    """获取审计日志记录器。

    Returns:
        AuditLogger 实例。
    """
    return audit_logger


def get_orchestrator():
    """获取编译后的主编排 StateGraph（懒加载）。

    组装块 C 的 4 个 Layer Graph 到 Orchestrator。
    使用全局注入的 Checkpointer（PostgresSaver 或 MemorySaver）。

    Returns:
        编译后的主编排 StateGraph。
    """
    global _orchestrator_instance
    if _orchestrator_instance is not None:
        return _orchestrator_instance

    from app.analysis_layer.agent_graph import analysis_graph
    from app.evaluation.agent_graph import evaluation_graph
    from app.generation_layer.agent_graph import generation_graph
    from app.planning_layer.agent_graph import planning_graph
    from app.session_history.compressor import ContextCompressor
    from app.session_history.memory_retriever import MemoryRetriever

    # Phase 2-3: 注入记忆管理 Service
    _session_service = get_session_service()
    _context_compressor = ContextCompressor()
    _memory_retriever = MemoryRetriever()

    _orchestrator_instance = build_and_compile(
        analysis_graph=analysis_graph,
        planning_graph=planning_graph,
        generation_graph=generation_graph,
        evaluation_graph=evaluation_graph,
        retrieval_pipeline=None,
        checkpointer=_checkpointer_instance,
        session_service=_session_service,
        context_compressor=_context_compressor,
        memory_retriever=_memory_retriever,
    )
    return _orchestrator_instance


def get_session_service():
    """获取 SessionHistoryService 实例（懒加载）。

    Returns:
        SessionHistoryService 实例。
    """
    from app.session_history.service import SessionHistoryService

    return SessionHistoryService()
