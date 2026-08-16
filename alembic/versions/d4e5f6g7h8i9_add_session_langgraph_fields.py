"""add_session_langgraph_fields

Phase 3: 为 sessions 表添加 LangGraph 断点恢复字段。

Revision ID: d4e5f6g7h8i9
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6g7h8i9"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """添加 LangGraph 断点恢复字段。"""
    op.add_column("sessions", sa.Column("thread_id", sa.String(64), nullable=True, comment="LangGraph thread_id"))
    op.add_column("sessions", sa.Column("checkpoint_ts", sa.DateTime(timezone=True), nullable=True, comment="最后一次 checkpoint 时间"))
    op.add_column("sessions", sa.Column("current_node", sa.String(64), nullable=True, comment="当前所在 LangGraph 节点名"))
    op.add_column("sessions", sa.Column("interrupt_stage", sa.String(32), nullable=True, comment="被 interrupt 暂停的阶段"))
    op.create_index("ix_sessions_thread_id", "sessions", ["thread_id"])


def downgrade() -> None:
    """回退。"""
    op.drop_index("ix_sessions_thread_id", table_name="sessions")
    op.drop_column("sessions", "interrupt_stage")
    op.drop_column("sessions", "current_node")
    op.drop_column("sessions", "checkpoint_ts")
    op.drop_column("sessions", "thread_id")
