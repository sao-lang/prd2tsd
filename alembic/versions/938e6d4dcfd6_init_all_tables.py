"""init_all_tables — 创建所有表（块 A + 块 E 企业功能）

包含: users, organizations, workspaces, roles, team_members,
      llm_call_logs, budget_configs, sessions, session_messages, uploaded_documents

Revision ID: 938e6d4dcfd6
Revises: 
Create Date: 2026-07-23 18:23:01.251262
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# revision identifiers, used by Alembic.
revision: str = "938e6d4dcfd6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("auth_provider", sa.String(32), nullable=False, server_default="jwt"),
        sa.Column("auth_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("preferences", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("auth_provider", "auth_id", name="uq_user_auth"),
    )

    # --- organizations ---
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), unique=True, nullable=False),
        sa.Column("plan", sa.String(32), nullable=False, server_default="free"),
        sa.Column("settings", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # --- workspaces ---
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column(
            "knowledge_scope", sa.String(32),
            nullable=False, server_default="workspace",
        ),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "organization_id", "slug", name="uq_org_workspace_slug",
        ),
    )

    # --- roles ---
    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36),
            sa.ForeignKey("organizations.id"), nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("permissions", JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # --- team_members ---
    op.create_table(
        "team_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36),
            sa.ForeignKey("workspaces.id"), nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column(
            "role_id", sa.String(36),
            sa.ForeignKey("roles.id"), nullable=False,
        ),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    # --- llm_call_logs (块 E) ---
    op.create_table(
        "llm_call_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column(
            "workspace_id", sa.String(36),
            sa.ForeignKey("workspaces.id"), nullable=True,
        ),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("layer", sa.String(32), nullable=True),
        sa.Column("node", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cost", sa.Numeric(10, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("cached", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # --- budget_configs (块 E) ---
    op.create_table(
        "budget_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36),
            sa.ForeignKey("workspaces.id"), nullable=False, unique=True,
        ),
        sa.Column("monthly_budget_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "alert_threshold", sa.Numeric(3, 2),
            nullable=False, server_default="0.90",
        ),
        sa.Column(
            "auto_downgrade", sa.Boolean,
            nullable=False, server_default="true",
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # --- sessions (块 E) ---
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36),
            sa.ForeignKey("workspaces.id"), nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "session_type", sa.String(32),
            nullable=False, server_default="generate",
        ),
        sa.Column(
            "status", sa.String(16),
            nullable=False, server_default="active",
        ),
        sa.Column("source_prd_id", sa.String(36), nullable=True),
        sa.Column("source_task_id", sa.String(36), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "cost_usd", sa.Numeric(10, 6),
            nullable=False, server_default="0",
        ),
        sa.Column("rating", sa.SmallInteger, nullable=True),
        sa.Column("tags", ARRAY(sa.String), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "id", name="uq_workspace_session"),
    )
    op.create_index("idx_sessions_workspace_id", "sessions", ["workspace_id"])
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_created_at", "sessions", [sa.text("created_at DESC")])
    op.create_index(
        "idx_sessions_last_message_at", "sessions", [sa.text("last_message_at DESC")],
    )
    op.create_index("idx_sessions_status", "sessions", ["status"])

    # --- session_messages (块 E) ---
    op.create_table(
        "session_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id", sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "content_type", sa.String(32),
            nullable=False, server_default="text",
        ),
        sa.Column("attachments", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("parent_message_id", sa.String(36), nullable=True),
        sa.Column("turn_index", sa.Integer, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "cost_usd", sa.Numeric(10, 6),
            nullable=False, server_default="0",
        ),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("rating", sa.SmallInteger, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("session_id", "turn_index", name="uq_session_turn"),
    )
    op.create_index(
        "idx_messages_session_id", "session_messages", ["session_id"],
    )
    op.create_index(
        "idx_messages_created_at", "session_messages", ["created_at"],
    )

    # --- uploaded_documents (块 E) ---
    op.create_table(
        "uploaded_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36),
            sa.ForeignKey("workspaces.id"), nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("file_type", sa.String(32), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column(
            "processing_status", sa.String(32),
            nullable=False, server_default="pending",
        ),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("relation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "session_id", sa.String(36),
            sa.ForeignKey("sessions.id"), nullable=True,
        ),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("tags", ARRAY(sa.String), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_documents_workspace_id", "uploaded_documents", ["workspace_id"],
    )
    op.create_index(
        "idx_documents_user_id", "uploaded_documents", ["user_id"],
    )
    op.create_index(
        "idx_documents_file_type", "uploaded_documents", ["file_type"],
    )
    op.create_index(
        "idx_documents_processing_status", "uploaded_documents", ["processing_status"],
    )
    op.create_index(
        "idx_documents_created_at", "uploaded_documents",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_documents_file_hash", "uploaded_documents", ["file_hash"],
    )


def downgrade() -> None:
    op.drop_table("uploaded_documents")
    op.drop_table("session_messages")
    op.drop_table("sessions")
    op.drop_table("budget_configs")
    op.drop_table("llm_call_logs")
    op.drop_table("team_members")
    op.drop_table("roles")
    op.drop_table("workspaces")
    op.drop_table("organizations")
    op.drop_table("users")
