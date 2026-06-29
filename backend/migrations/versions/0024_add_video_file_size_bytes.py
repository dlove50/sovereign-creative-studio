"""add file_size_bytes to video_generations

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _columns("video_generations")
    if "file_size_bytes" not in cols:
        op.add_column(
            "video_generations",
            sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    cols = _columns("video_generations")
    if "file_size_bytes" in cols:
        op.drop_column("video_generations", "file_size_bytes")
