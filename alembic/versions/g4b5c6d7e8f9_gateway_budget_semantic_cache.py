"""Add periodic budgets and persistent semantic cache.

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "g4b5c6d7e8f9"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """增加周/月预算字段与语义缓存表。"""
    op.add_column("budget_configs", sa.Column("weekly_budget_usd", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "budget_configs",
        sa.Column("budget_period", sa.String(16), nullable=False, server_default="monthly"),
    )
    op.create_table(
        "semantic_cache_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, server_default=""),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("guardrail_version", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "workspace_id",
            "task_type",
            "model",
            "prompt_hash",
            "embedding_model",
            "guardrail_version",
            name="uq_semantic_cache_scope_hash",
        ),
    )
    op.create_index("ix_semantic_cache_entries_workspace_id", "semantic_cache_entries", ["workspace_id"])
    op.create_index("ix_semantic_cache_entries_task_type", "semantic_cache_entries", ["task_type"])
    op.create_index("ix_semantic_cache_entries_expires_at", "semantic_cache_entries", ["expires_at"])
    op.create_index(
        "ix_semantic_cache_lookup",
        "semantic_cache_entries",
        ["workspace_id", "task_type", "model", "expires_at"],
    )


def downgrade() -> None:
    """移除语义缓存表与周期预算字段。"""
    op.drop_index("ix_semantic_cache_lookup", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_expires_at", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_task_type", table_name="semantic_cache_entries")
    op.drop_index("ix_semantic_cache_entries_workspace_id", table_name="semantic_cache_entries")
    op.drop_table("semantic_cache_entries")
    op.drop_column("budget_configs", "budget_period")
    op.drop_column("budget_configs", "weekly_budget_usd")
