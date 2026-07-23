"""数据模型单元测试。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.role import Role
from app.models.team_member import TeamMember
from app.models.user import User
from app.models.workspace import Workspace


@pytest.mark.asyncio
async def test_user_model_fields(db_session: AsyncSession):
    """验证 User 模型所有字段类型正确。"""
    user = User(
        email="test@example.com",
        display_name="测试用户",
        hashed_password="hashed_pw",
        auth_provider="jwt",
        auth_id="test@example.com",
    )
    db_session.add(user)
    await db_session.commit()

    assert user.id is not None
    assert isinstance(user.id, str)
    assert len(user.id) == 36  # UUID 字符串长度
    assert user.email == "test@example.com"
    assert user.display_name == "测试用户"
    assert user.auth_provider == "jwt"
    assert user.status == "active"


@pytest.mark.asyncio
async def test_workspace_unique_constraint(db_session: AsyncSession):
    """验证同一 organization 下 slug 唯一。"""
    org = Organization(name="测试组织", slug="test-org")
    db_session.add(org)
    await db_session.flush()

    ws1 = Workspace(organization_id=org.id, name="WS1", slug="test-ws")
    db_session.add(ws1)
    await db_session.flush()

    with pytest.raises(Exception):
        ws2 = Workspace(organization_id=org.id, name="WS2", slug="test-ws")
        db_session.add(ws2)
        await db_session.flush()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_team_member_relationship(db_session: AsyncSession):
    """验证 User → Workspace 多对多关系通过 team_members 正确建立。"""
    # 创建组织
    org = Organization(name="测试组织", slug="rel-org")
    db_session.add(org)
    await db_session.flush()

    # 创建用户
    user = User(
        email="rel@example.com",
        display_name="关系测试",
        hashed_password="pw",
        auth_provider="jwt",
        auth_id="rel@example.com",
    )
    db_session.add(user)
    await db_session.flush()

    # 创建工作空间
    ws = Workspace(organization_id=org.id, name="关系WS", slug="rel-ws")
    db_session.add(ws)
    await db_session.flush()

    # 创建角色
    role = Role(organization_id=org.id, name="admin", is_system=True, permissions=["read"])
    db_session.add(role)
    await db_session.flush()

    # 添加团队成员
    member = TeamMember(workspace_id=ws.id, user_id=user.id, role_id=role.id)
    db_session.add(member)
    await db_session.commit()

    # 验证关系
    result = await db_session.execute(
        select(TeamMember).where(TeamMember.user_id == user.id)
    )
    members = result.scalars().all()
    assert len(members) == 1
    assert str(members[0].workspace_id) == str(ws.id)


@pytest.mark.asyncio
async def test_organization_model(db_session: AsyncSession):
    """验证组织模型创建。"""
    org = Organization(
        name="企业组织",
        slug="enterprise",
        plan="pro",
        settings={"feature_audit": True},
    )
    db_session.add(org)
    await db_session.commit()

    assert str(org.id) is not None
    assert org.name == "企业组织"
    assert org.slug == "enterprise"
    assert org.plan == "pro"
    assert org.settings == {"feature_audit": True}
