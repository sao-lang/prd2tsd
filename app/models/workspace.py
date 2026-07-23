"""工作空间模型（多租户单元）。"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Workspace(UUIDMixin, TimestampMixin, Base):
    """工作空间模型。"""

    __tablename__ = "workspaces"

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="workspace")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_org_workspace_slug"),
    )

    # 关系
    organization = relationship("Organization", back_populates="workspaces")
    team_members = relationship("TeamMember", back_populates="workspace", lazy="selectin")
