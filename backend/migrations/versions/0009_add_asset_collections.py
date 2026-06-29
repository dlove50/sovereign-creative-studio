"""add asset_collections table

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("asset_collections"):
        return
    op.create_table(
        "asset_collections",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("asset_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_asset_collections_user_id", "asset_collections", ["user_id"])
    op.create_index("ix_asset_collections_project_id", "asset_collections", ["project_id"])


def downgrade() -> None:
    if _has_table("asset_collections"):
        op.drop_table("asset_collections")
