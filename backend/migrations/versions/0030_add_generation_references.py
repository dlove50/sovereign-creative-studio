"""reference images for image edits

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("generations")}
    if "reference_image_urls" not in columns:
        op.add_column("generations", sa.Column("reference_image_urls", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("generations")}
    if "reference_image_urls" in columns:
        with op.batch_alter_table("generations") as batch:
            batch.drop_column("reference_image_urls")
