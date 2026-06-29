"""add video studio: video mode column, storyboards, shots (Phase C11)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_column("video_generations", "mode"):
        op.add_column(
            "video_generations",
            sa.Column(
                "mode",
                sa.String(length=24),
                nullable=False,
                server_default="image_to_video",
            ),
        )

    if not _has_table("storyboards"):
        op.create_table(
            "storyboards",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_storyboards_user_id", "storyboards", ["user_id"])
        op.create_index("ix_storyboards_project_id", "storyboards", ["project_id"])

    if not _has_table("shots"):
        op.create_table(
            "shots",
            sa.Column("id", sa.String(length=32), primary_key=True),
            sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("storyboard_id", sa.String(length=32), sa.ForeignKey("storyboards.id"), nullable=False),
            sa.Column("shot_number", sa.Integer(), nullable=False),
            sa.Column("duration_seconds", sa.Integer(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("camera_notes", sa.Text(), nullable=True),
            sa.Column("generation_prompt", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_shots_user_id", "shots", ["user_id"])
        op.create_index("ix_shots_storyboard_id", "shots", ["storyboard_id"])


def downgrade() -> None:
    op.drop_table("shots")
    op.drop_table("storyboards")
    if _has_column("video_generations", "mode"):
        op.drop_column("video_generations", "mode")
