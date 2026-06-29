"""add video_generations table (image-to-video foundation)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Guarded so a legacy create_all database that already has this table is a
    # safe no-op, consistent with migrations 0002/0003.
    if _has_table("video_generations"):
        return
    op.create_table(
        "video_generations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("product_scene_id", sa.String(length=32), sa.ForeignKey("product_scene_generations.id"), nullable=True),
        sa.Column("source_image_url", sa.String(length=512), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("motion_preset", sa.String(length=32), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_url", sa.String(length=512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_video_generations_user_id", "video_generations", ["user_id"])
    op.create_index("ix_video_generations_project_id", "video_generations", ["project_id"])
    op.create_index(
        "ix_video_generations_product_scene_id", "video_generations", ["product_scene_id"]
    )


def downgrade() -> None:
    op.drop_table("video_generations")
