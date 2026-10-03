"""interactive (branching) videos

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "interactive_videos" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "interactive_videos",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="Untitled interactive video"),
        sa.Column("nodes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("start_node_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_interactive_videos_user_id", "interactive_videos", ["user_id"])


def downgrade() -> None:
    if "interactive_videos" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_interactive_videos_user_id", table_name="interactive_videos")
        op.drop_table("interactive_videos")
