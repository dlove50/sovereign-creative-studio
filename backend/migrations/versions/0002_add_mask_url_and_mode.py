"""add product_assets.mask_url and product_scene_generations.mode

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15

The column adds are guarded by an inspector check so this migration is also safe
to run against a legacy database that was created by the old create_all() and
already happens to have these columns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column("product_assets", "mask_url"):
        op.add_column(
            "product_assets",
            sa.Column("mask_url", sa.String(length=512), nullable=True),
        )
    if not _has_column("product_scene_generations", "mode"):
        op.add_column(
            "product_scene_generations",
            sa.Column("mode", sa.String(length=16), nullable=True),
        )


def downgrade() -> None:
    if _has_column("product_scene_generations", "mode"):
        op.drop_column("product_scene_generations", "mode")
    if _has_column("product_assets", "mask_url"):
        op.drop_column("product_assets", "mask_url")
