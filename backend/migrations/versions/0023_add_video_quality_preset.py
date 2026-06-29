"""add video quality preset

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _columns("video_generations")
    if "quality_preset" not in cols:
        op.add_column(
            "video_generations",
            sa.Column("quality_preset", sa.String(length=40), nullable=True),
        )


def downgrade() -> None:
    cols = _columns("video_generations")
    if "quality_preset" in cols:
        op.drop_column("video_generations", "quality_preset")
