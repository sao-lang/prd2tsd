"""组织模型。"""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Organization(UUIDMixin, TimestampMixin, Base):
    """组织模型。"""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # 关系
    workspaces = relationship("Workspace", back_populates="organization", lazy="selectin")
    roles = relationship("Role", back_populates="organization", lazy="selectin")
