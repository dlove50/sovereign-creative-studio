"""add production_projects table

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("production_projects"):
        return
    op.create_table(
        "production_projects",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("storyboard_ids", sa.JSON(), nullable=False),
        sa.Column("shot_ids", sa.JSON(), nullable=False),
        sa.Column("video_ids", sa.JSON(), nullable=False),
        sa.Column("export_urls", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_production_projects_user_id", "production_projects", ["user_id"])
    op.create_index("ix_production_projects_project_id", "production_projects", ["project_id"])


def downgrade() -> None:
    if _has_table("production_projects"):
        op.drop_table("production_projects")
