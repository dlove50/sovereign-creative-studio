"""add target_attribute to product_scene_generations

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if _has_column("product_scene_generations", "target_attribute"):
        return
    op.add_column(
        "product_scene_generations",
        sa.Column("target_attribute", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    if _has_column("product_scene_generations", "target_attribute"):
        op.drop_column("product_scene_generations", "target_attribute")
