"""工作空间单元测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.workspace import Workspace


@pytest.mark.asyncio
async def test_create_workspace(db_session: AsyncSession):
    """验证创建工作空间。"""
    org = Organization(name="测试组织", slug="ws-test-org")
    db_session.add(org)
    await db_session.flush()

    ws = Workspace(
        organization_id=org.id,
        name="测试工作空间",
        slug="test-ws",
    )
    db_session.add(ws)
    await db_session.commit()

    assert ws.id is not None
    assert ws.name == "测试工作空间"
    assert ws.slug == "test-ws"
    assert ws.is_archived is False
    assert ws.knowledge_scope == "workspace"


@pytest.mark.asyncio
async def test_workspace_archive(db_session: AsyncSession):
    """验证工作空间归档。"""
    org = Organization(name="归档测试", slug="archive-org")
    db_session.add(org)
    await db_session.flush()

    ws = Workspace(organization_id=org.id, name="归档WS", slug="archive-ws")
    db_session.add(ws)
    await db_session.commit()

    ws.is_archived = True
    await db_session.commit()

    assert ws.is_archived is True
