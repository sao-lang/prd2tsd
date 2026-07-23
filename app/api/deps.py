"""全局依赖注入。"""

from __future__ import annotations

from app.core.connections import connection_manager
from app.llm_gateway import config_manager, gateway
from app.security.audit_logger import audit_logger
from app.security.data_masking import DataMaskingEngine


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
    """获取数据脱敏引擎。

    Returns:
        DataMaskingEngine 实例。
    """
    return DataMaskingEngine()


def get_audit_logger():
    """获取审计日志记录器。

    Returns:
        AuditLogger 实例。
    """
    return audit_logger
