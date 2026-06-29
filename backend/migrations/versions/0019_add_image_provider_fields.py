"""add image generation provider metadata

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _columns("generations")
    if "provider" not in cols:
        op.add_column(
            "generations",
            sa.Column(
                "provider",
                sa.String(length=32),
                nullable=False,
                server_default="local_comfyui",
            ),
        )
    if "provider_task_id" not in cols:
        op.add_column(
            "generations",
            sa.Column("provider_task_id", sa.String(length=255), nullable=True),
        )
    if "provider_model" not in cols:
        op.add_column(
            "generations",
            sa.Column("provider_model", sa.String(length=120), nullable=True),
        )
    if "source_image_url" not in cols:
        op.add_column(
            "generations",
            sa.Column("source_image_url", sa.String(length=512), nullable=True),
        )


def downgrade() -> None:
    cols = _columns("generations")
    if "source_image_url" in cols:
        op.drop_column("generations", "source_image_url")
    if "provider_model" in cols:
        op.drop_column("generations", "provider_model")
    if "provider_task_id" in cols:
        op.drop_column("generations", "provider_task_id")
    if "provider" in cols:
        op.drop_column("generations", "provider")
