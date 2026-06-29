"""add sandbox_topups table (local fake/test top-up sandbox)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("sandbox_topups"):
        return
    op.create_table(
        "sandbox_topups",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("package_id", sa.String(length=32), nullable=False),
        sa.Column("package_name", sa.String(length=80), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="CAD"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("credit_transaction_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sandbox_topups_user_id", "sandbox_topups", ["user_id"])


def downgrade() -> None:
    if _has_table("sandbox_topups"):
        op.drop_table("sandbox_topups")
