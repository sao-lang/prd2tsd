"""角色模型。"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Role(UUIDMixin, TimestampMixin, Base):
    """角色模型（系统预置 + 自定义）。"""

    __tablename__ = "roles"

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # 关系
    organization = relationship("Organization", back_populates="roles")
