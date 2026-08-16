"""add_batch_tasks_and_doc_link — 批量任务落库 + 向量块文档关联

包含:
- batch_tasks 表（BatchTaskService 重启可恢复，2026-08-16 条目 31）
- text_unit_embeddings.document_id 列（文档语义搜索关联，表不存在时跳过）

Revision ID: f3a4b5c6d7e8
Revises: e2f3g4h5i6j7
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e2f3g4h5i6j7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """升级：建 batch_tasks 表 + 为向量块表补 document_id 列。"""
    op.create_table(
        "batch_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_batch_tasks_workspace", "batch_tasks", ["workspace_id"])

    # text_unit_embeddings 由运行时 ensure_extensions 创建（非 ORM），
    # 迁移执行时表可能不存在，故用 DO 块 + IF EXISTS 保护。
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT FROM pg_tables WHERE schemaname='public' "
        "AND tablename='text_unit_embeddings') THEN "
        "ALTER TABLE text_unit_embeddings "
        "ADD COLUMN IF NOT EXISTS document_id VARCHAR(64) DEFAULT ''; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    """回滚：删 batch_tasks 表 + 移除 document_id 列。"""
    op.drop_index("idx_batch_tasks_workspace", table_name="batch_tasks")
    op.drop_table("batch_tasks")
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT FROM pg_tables WHERE schemaname='public' "
        "AND tablename='text_unit_embeddings') THEN "
        "ALTER TABLE text_unit_embeddings DROP COLUMN IF EXISTS document_id; "
        "END IF; END $$;"
    )
