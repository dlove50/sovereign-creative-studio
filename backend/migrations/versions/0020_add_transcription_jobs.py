"""add local video transcription jobs

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "transcription_jobs" in _tables():
        return
    op.create_table(
        "transcription_jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("source_video_url", sa.String(length=512), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("detected_language", sa.String(length=40), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="local_whisper"),
        sa.Column("model_name", sa.String(length=80), nullable=False, server_default="base"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("credits_cost", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_transcription_jobs_user_id", "transcription_jobs", ["user_id"])
    op.create_index("ix_transcription_jobs_project_id", "transcription_jobs", ["project_id"])


def downgrade() -> None:
    if "transcription_jobs" not in _tables():
        return
    op.drop_index("ix_transcription_jobs_project_id", table_name="transcription_jobs")
    op.drop_index("ix_transcription_jobs_user_id", table_name="transcription_jobs")
    op.drop_table("transcription_jobs")
