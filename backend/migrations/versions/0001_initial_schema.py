"""initial schema (baseline, pre product mask/mode)

Revision ID: 0001
Revises:
Create Date: 2026-06-15

Represents the schema as it existed through Phase 7 — i.e. everything except
product_assets.mask_url and product_scene_generations.mode, which migration 0002
adds. A legacy database created by the old Base.metadata.create_all() is stamped
at this revision on startup so 0002 can bring it up to date without a reset.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "generations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("file_url", sa.String(length=512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("credits_cost", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_generations_user_id", "generations", ["user_id"])
    op.create_index("ix_generations_project_id", "generations", ["project_id"])

    op.create_table(
        "product_assets",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_url", sa.String(length=512), nullable=False),
        sa.Column("processed_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_product_assets_user_id", "product_assets", ["user_id"])
    op.create_index("ix_product_assets_project_id", "product_assets", ["project_id"])

    op.create_table(
        "product_scene_generations",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.String(length=32), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("asset_id", sa.String(length=32), sa.ForeignKey("product_assets.id"), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("preset", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_url", sa.String(length=512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_product_scene_generations_user_id", "product_scene_generations", ["user_id"])
    op.create_index("ix_product_scene_generations_project_id", "product_scene_generations", ["project_id"])
    op.create_index("ix_product_scene_generations_asset_id", "product_scene_generations", ["asset_id"])

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.String(length=32), sa.ForeignKey("generations.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"])


def downgrade() -> None:
    op.drop_table("credit_transactions")
    op.drop_table("product_scene_generations")
    op.drop_table("product_assets")
    op.drop_table("generations")
    op.drop_table("projects")
    op.drop_table("users")
