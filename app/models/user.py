"""用户模型。"""

from __future__ import annotations

from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    """用户账号模型。"""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="jwt")
    auth_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("auth_provider", "auth_id", name="uq_user_auth"),
    )

    # 关系
    team_memberships = relationship("TeamMember", back_populates="user", lazy="selectin")
