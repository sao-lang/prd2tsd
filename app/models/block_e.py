"""块 E 企业功能数据模型。

包含：LLM Call Logs、Budget Configs、Sessions、Session Messages、Uploaded Documents。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class LLMCallLog(UUIDMixin, Base):
    """每次 LLM 调用记录 — 成本追踪与审计。"""

    __tablename__ = "llm_call_logs"

    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=True,
    )
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    layer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )


class BudgetConfig(UUIDMixin, Base):
    """工作空间预算配置。"""

    __tablename__ = "budget_configs"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), unique=True, nullable=False,
    )
    monthly_budget_usd: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True,
    )
    alert_threshold: Mapped[float] = mapped_column(
        Numeric(3, 2), default=0.90,
    )
    auto_downgrade: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class Session(UUIDMixin, TimestampMixin, Base):
    """会话模型。"""

    __tablename__ = "sessions"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    session_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="generate",
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source_prd_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_workspace_session"),
    )


class SessionMessage(UUIDMixin, Base):
    """会话消息模型。"""

    __tablename__ = "session_messages"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), default="text")
    attachments: Mapped[dict | None] = mapped_column(JSON, default=list)
    msg_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, default=dict)
    parent_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("session_id", "turn_index", name="uq_session_turn"),
    )


class UploadedDocument(UUIDMixin, TimestampMixin, Base):
    """已上传文档模型。"""

    __tablename__ = "uploaded_documents"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id"), nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending",
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    relation_count: Mapped[int] = mapped_column(Integer, default=0)
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id"), nullable=True,
    )
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
