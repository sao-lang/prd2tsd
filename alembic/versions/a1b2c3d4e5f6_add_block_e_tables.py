"""add_block_e_tables — 修复 Block E 表类型不一致

注意：5 张 Block E 表（llm_call_logs / budget_configs / sessions /
session_messages / uploaded_documents）已在迁移 1 中创建。
本迁移仅修复类型不一致问题：
  - sessions.tags: ARRAY(String) → JSONB（对齐 ORM 的 JSON 类型）
  - uploaded_documents.tags: ARRAY(String) → JSONB

Revision ID: a1b2c3d4e5f6
Revises: 938e6d4dcfd6
Create Date: 2026-07-24 15:50:00
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "938e6d4dcfd6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 修复 sessions.tags 类型：ARRAY(String) → JSONB
    op.execute(
        "ALTER TABLE sessions ALTER COLUMN tags TYPE JSONB "
        "USING CASE WHEN tags IS NULL THEN NULL ELSE to_jsonb(tags::text) END"
    )

    # 修复 uploaded_documents.tags 类型：ARRAY(String) → JSONB
    op.execute(
        "ALTER TABLE uploaded_documents ALTER COLUMN tags TYPE JSONB "
        "USING CASE WHEN tags IS NULL THEN NULL ELSE to_jsonb(tags::text) END"
    )


def downgrade() -> None:
    # 回退：JSONB → ARRAY(String)
    op.execute(
        "ALTER TABLE sessions ALTER COLUMN tags TYPE VARCHAR(255)[] "
        "USING CASE WHEN tags IS NULL THEN NULL "
        "ELSE ARRAY(SELECT jsonb_array_elements_text(tags)) END"
    )
    op.execute(
        "ALTER TABLE uploaded_documents ALTER COLUMN tags TYPE VARCHAR(255)[] "
        "USING CASE WHEN tags IS NULL THEN NULL "
        "ELSE ARRAY(SELECT jsonb_array_elements_text(tags)) END"
    )

