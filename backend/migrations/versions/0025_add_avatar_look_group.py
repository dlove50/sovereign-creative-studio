"""group avatar looks under their base avatar

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _columns("avatar_assets")
    if "group_id" not in cols:
        op.add_column("avatar_assets", sa.Column("group_id", sa.String(32), nullable=True))
        op.create_index("ix_avatar_assets_group_id", "avatar_assets", ["group_id"])
    if "look_label" not in cols:
        op.add_column("avatar_assets", sa.Column("look_label", sa.String(160), nullable=True))


def downgrade() -> None:
    cols = _columns("avatar_assets")
    if "group_id" in cols:
        op.drop_index("ix_avatar_assets_group_id", table_name="avatar_assets")
        op.drop_column("avatar_assets", "group_id")
    if "look_label" in cols:
        op.drop_column("avatar_assets", "look_label")
