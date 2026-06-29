"""add generation links to shots

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column("shots", "product_scene_id"):
        op.add_column(
            "shots",
            sa.Column("product_scene_id", sa.String(length=32), nullable=True),
        )
        op.create_index("ix_shots_product_scene_id", "shots", ["product_scene_id"])
    if not _has_column("shots", "video_id"):
        op.add_column("shots", sa.Column("video_id", sa.String(length=32), nullable=True))
        op.create_index("ix_shots_video_id", "shots", ["video_id"])


def downgrade() -> None:
    if _has_column("shots", "video_id"):
        op.drop_index("ix_shots_video_id", table_name="shots")
        op.drop_column("shots", "video_id")
    if _has_column("shots", "product_scene_id"):
        op.drop_index("ix_shots_product_scene_id", table_name="shots")
        op.drop_column("shots", "product_scene_id")
