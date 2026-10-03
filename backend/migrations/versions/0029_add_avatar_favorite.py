"""favorite flag on avatars

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("avatar_assets")}
    if "is_favorite" not in columns:
        op.add_column("avatar_assets", sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("avatar_assets")}
    if "is_favorite" in columns:
        with op.batch_alter_table("avatar_assets") as batch:
            batch.drop_column("is_favorite")
