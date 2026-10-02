"""scene-by-scene movies

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "movies" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "movies",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="Untitled video"),
        sa.Column("orientation", sa.String(16), nullable=False, server_default="portrait"),
        sa.Column("scenes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("output_video_path", sa.String(512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_movies_user_id", "movies", ["user_id"])


def downgrade() -> None:
    if "movies" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_movies_user_id", table_name="movies")
        op.drop_table("movies")
