"""add copy_generations table (AI Copy Studio)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Guarded so a legacy create_all database that already has this table (stamped
    # at the baseline and upgraded) is a safe no-op, mirroring migration 0002.
    if _has_table("copy_generations"):
        return
    op.create_table(
        "copy_generations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("product_asset_id", sa.String(length=32), sa.ForeignKey("product_assets.id"), nullable=True),
        sa.Column("product_scene_id", sa.String(length=32), sa.ForeignKey("product_scene_generations.id"), nullable=True),
        sa.Column("copy_type", sa.String(length=32), nullable=False),
        sa.Column("tone", sa.String(length=32), nullable=False),
        sa.Column("audience", sa.String(length=255), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_copy_generations_user_id", "copy_generations", ["user_id"])
    op.create_index("ix_copy_generations_project_id", "copy_generations", ["project_id"])
    op.create_index("ix_copy_generations_product_asset_id", "copy_generations", ["product_asset_id"])
    op.create_index("ix_copy_generations_product_scene_id", "copy_generations", ["product_scene_id"])


def downgrade() -> None:
    op.drop_table("copy_generations")
