"""add username + password_hash to users for real accounts

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _columns("users")
    if "username" not in cols:
        op.add_column("users", sa.Column("username", sa.String(length=120), nullable=True))
        op.create_index("ix_users_username", "users", ["username"], unique=True)
    if "password_hash" not in cols:
        op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    cols = _columns("users")
    if "password_hash" in cols:
        op.drop_column("users", "password_hash")
    if "username" in cols:
        op.drop_index("ix_users_username", table_name="users")
        op.drop_column("users", "username")
