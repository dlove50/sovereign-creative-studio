"""add campaign_bundles table (one-click Campaign Builder)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Guarded so a legacy create_all database that already has this table is a
    # safe no-op, consistent with migrations 0002-0006.
    if _has_table("campaign_bundles"):
        return
    op.create_table(
        "campaign_bundles",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("brief_id", sa.String(length=32), sa.ForeignKey("creative_briefs.id"), nullable=True),
        sa.Column("selected_asset_id", sa.String(length=32), sa.ForeignKey("product_assets.id"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("campaign_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scene_ids", sa.JSON(), nullable=False),
        sa.Column("copy_ids", sa.JSON(), nullable=False),
        sa.Column("video_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_campaign_bundles_user_id", "campaign_bundles", ["user_id"])
    op.create_index("ix_campaign_bundles_project_id", "campaign_bundles", ["project_id"])


def downgrade() -> None:
    op.drop_table("campaign_bundles")
