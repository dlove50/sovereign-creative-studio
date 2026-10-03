"""default voice per avatar

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("avatar_assets")}
    if "default_voice_id" not in columns:
        op.add_column("avatar_assets", sa.Column("default_voice_id", sa.String(200), nullable=True))


def downgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("avatar_assets")}
    if "default_voice_id" in columns:
        with op.batch_alter_table("avatar_assets") as batch:
            batch.drop_column("default_voice_id")
