"""add deleted_at soft-delete columns for trash/recovery

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_TABLES = (
    "generations",
    "product_assets",
    "product_scene_generations",
    "video_generations",
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table in _TABLES:
        if "deleted_at" not in _columns(table):
            op.add_column(table, sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        if "deleted_at" in _columns(table):
            op.drop_column(table, "deleted_at")
