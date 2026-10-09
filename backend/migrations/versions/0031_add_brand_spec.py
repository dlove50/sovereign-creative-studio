"""brand spec (named colors, fonts, logos, assets) on projects

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("projects")}
    if "brand_spec_json" not in columns:
        op.add_column("projects", sa.Column("brand_spec_json", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("projects")}
    if "brand_spec_json" in columns:
        with op.batch_alter_table("projects") as batch:
            batch.drop_column("brand_spec_json")
