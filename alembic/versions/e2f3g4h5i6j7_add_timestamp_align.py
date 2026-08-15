"""add_timestamp_align — organizations/roles 补 updated_at（对齐 TimestampMixin）

Registration 流程会 INSERT Organization/Role，缺少 updated_at 列将导致
UndefinedColumnError（2026-08-15 真实库冒烟发现）。

Revision ID: e2f3g4h5i6j7
Revises: e1f2g3h4i5j6
Create Date: 2026-08-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3g4h5i6j7"
down_revision: str | None = "e1f2g3h4i5j6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """升级：为 organizations/roles 补充 updated_at 列。"""
    op.add_column(
        "organizations",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.add_column(
        "roles",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """回滚。"""
    op.drop_column("roles", "updated_at")
    op.drop_column("organizations", "updated_at")
