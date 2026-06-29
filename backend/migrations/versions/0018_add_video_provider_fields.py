"""add video provider metadata and per-job video credit cost

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _columns("video_generations")
    if "provider" not in cols:
        op.add_column(
            "video_generations",
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="local_ltx"),
        )
    if "provider_task_id" not in cols:
        op.add_column(
            "video_generations",
            sa.Column("provider_task_id", sa.String(length=255), nullable=True),
        )
    if "credits_cost" not in cols:
        op.add_column(
            "video_generations",
            sa.Column("credits_cost", sa.Integer(), nullable=False, server_default="10"),
        )


def downgrade() -> None:
    cols = _columns("video_generations")
    if "credits_cost" in cols:
        op.drop_column("video_generations", "credits_cost")
    if "provider_task_id" in cols:
        op.drop_column("video_generations", "provider_task_id")
    if "provider" in cols:
        op.drop_column("video_generations", "provider")
