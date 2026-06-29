"""add avatar & voice foundation tables (Phase 16A)

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("avatar_assets"):
        op.create_table(
            "avatar_assets",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("avatar_type", sa.String(length=24), nullable=False, server_default="photo_avatar"),
            sa.Column("source_asset_id", sa.String(length=32), nullable=True),
            sa.Column("source_file_path", sa.String(length=512), nullable=True),
            sa.Column("thumbnail_path", sa.String(length=512), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
            sa.Column("provider", sa.String(length=24), nullable=False, server_default="local"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_avatar_assets_user_id", "avatar_assets", ["user_id"])

    if not _has_table("voice_assets"):
        op.create_table(
            "voice_assets",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("voice_type", sa.String(length=24), nullable=False, server_default="preset"),
            sa.Column("provider", sa.String(length=24), nullable=False, server_default="placeholder"),
            sa.Column("sample_file_path", sa.String(length=512), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_voice_assets_user_id", "voice_assets", ["user_id"])

    if not _has_table("avatar_jobs"):
        op.create_table(
            "avatar_jobs",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("avatar_id", sa.String(length=32), sa.ForeignKey("avatar_assets.id"), nullable=True),
            sa.Column("voice_id", sa.String(length=32), sa.ForeignKey("voice_assets.id"), nullable=True),
            sa.Column("job_type", sa.String(length=24), nullable=False, server_default="avatar_greeting"),
            sa.Column("script_text", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
            sa.Column("provider", sa.String(length=24), nullable=False, server_default="placeholder"),
            sa.Column("output_video_path", sa.String(length=512), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("credits_cost", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_avatar_jobs_user_id", "avatar_jobs", ["user_id"])


def downgrade() -> None:
    for table in ("avatar_jobs", "voice_assets", "avatar_assets"):
        if _has_table(table):
            op.drop_table(table)
