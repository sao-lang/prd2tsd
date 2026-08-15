"""add_persistence_and_align_tables — 任务/Webhook/评测分数持久化 + ORM 对齐

包含:
- task_runs / webhook_subscriptions / evaluation_scores（重启可恢复）
- roles.organization_id 对齐 ORM（nullable=True）
- team_members 补 created_at / updated_at（对齐 TimestampMixin）

Revision ID: e1f2g3h4i5j6
Revises: d4e5f6g7h8i9
Create Date: 2026-08-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2g3h4i5j6"
down_revision: str | None = "d4e5f6g7h8i9"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """升级：建持久化表 + 对齐列。"""
    # ── 任务运行记录（TaskManager 重启恢复）──
    op.create_table(
        "task_runs",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("thread_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("progress", sa.Float, nullable=False, server_default="0"),
        sa.Column("stage", sa.String(64), nullable=False, server_default=""),
        sa.Column("interrupt_stage", sa.String(64), nullable=False, server_default=""),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("evaluation", sa.JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_task_runs_status", "task_runs", ["status"])

    # ── Webhook 订阅（重启不丢注册）──
    op.create_table(
        "webhook_subscriptions",
        sa.Column("workspace_id", sa.String(36), primary_key=True),
        sa.Column("event", sa.String(64), primary_key=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── 评测分数历史（ScoreCalibrator 数据源）──
    op.create_table(
        "evaluation_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("overall_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("dimension_scores", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_eval_scores_created", "evaluation_scores", ["created_at"])

    # ── 对齐 roles.organization_id（ORM nullable=True）──
    op.alter_column("roles", "organization_id", nullable=True)

    # ── 对齐 team_members：补 created_at / updated_at（TimestampMixin）──
    op.add_column(
        "team_members",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "team_members",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """回滚。"""
    op.drop_index("idx_eval_scores_created", table_name="evaluation_scores")
    op.drop_table("evaluation_scores")
    op.drop_table("webhook_subscriptions")
    op.drop_index("idx_task_runs_status", table_name="task_runs")
    op.drop_table("task_runs")
    op.alter_column("roles", "organization_id", nullable=False)
    op.drop_column("team_members", "updated_at")
    op.drop_column("team_members", "created_at")
