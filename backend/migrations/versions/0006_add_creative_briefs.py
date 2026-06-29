"""add creative_briefs table (campaign planning)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # Guarded so a legacy create_all database that already has this table is a
    # safe no-op, consistent with migrations 0002-0004.
    if _has_table("creative_briefs"):
        return
    op.create_table(
        "creative_briefs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("campaign_goal", sa.Text(), nullable=True),
        sa.Column("target_channels", sa.Text(), nullable=True),
        sa.Column("deliverables", sa.Text(), nullable=True),
        sa.Column("key_messages", sa.Text(), nullable=True),
        sa.Column("creative_direction", sa.Text(), nullable=True),
        sa.Column("reference_notes", sa.Text(), nullable=True),
        sa.Column("selected_asset_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_creative_briefs_project_id", "creative_briefs", ["project_id"])


def downgrade() -> None:
    op.drop_table("creative_briefs")
