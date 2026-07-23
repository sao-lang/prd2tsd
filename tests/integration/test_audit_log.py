"""审计日志集成测试。"""

from __future__ import annotations

import pytest

from app.security.audit_logger import AuditLogger


@pytest.mark.asyncio
async def test_audit_log_basic():
    """验证审计日志基本功能。"""
    logger = AuditLogger()
    entry = await logger.log(
        action="create",
        resource="document",
        resource_id="doc-123",
        user_id="user-1",
        org_id="org-1",
        workspace_id="ws-1",
        detail={"title": "test"},
    )
    assert entry.id is not None
    assert entry.current_hash is not None


@pytest.mark.asyncio
async def test_audit_log_chain():
    """验证审计日志链。"""
    logger = AuditLogger()
    e1 = await logger.log(action="create", resource="ws", resource_id="1", user_id="u1")
    e2 = await logger.log(action="update", resource="ws", resource_id="1", user_id="u1")
    e3 = await logger.log(action="delete", resource="ws", resource_id="1", user_id="u1")

    assert e2.previous_hash == e1.current_hash
    assert e3.previous_hash == e2.current_hash
    assert logger.verify_hash_chain() is True
