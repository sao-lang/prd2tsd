"""团队成员模型。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class TeamMember(UUIDMixin, TimestampMixin, Base):
    """团队成员模型。"""

    __tablename__ = "team_members"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )
    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("roles.id"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
    )

    # 关系
    workspace = relationship("Workspace", back_populates="team_members")
    user = relationship("User", back_populates="team_memberships")
