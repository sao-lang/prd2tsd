"""持久化模型 — 任务运行 / Webhook 订阅 / 评测分数（重启可恢复）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class TaskRun(Base):
    """任务运行记录（TaskManager 持久化，重启后可恢复断点索引）。"""

    __tablename__ = "task_runs"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    thread_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    interrupt_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )


class WebhookSubscription(Base):
    """Webhook 订阅（持久化，重启不丢注册）。"""

    __tablename__ = "webhook_subscriptions"

    workspace_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )


class EvaluationScore(UUIDMixin, Base):
    """评测分数历史（ScoreCalibrator 历史比对数据源）。"""

    __tablename__ = "evaluation_scores"

    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dimension_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
