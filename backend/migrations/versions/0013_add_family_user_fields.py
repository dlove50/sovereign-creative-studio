"""add family user management fields

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column("users", "role"):
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=24), nullable=False, server_default="family_user"),
        )
    if not _has_column("users", "status"):
        op.add_column(
            "users",
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        )
    if not _has_column("users", "notes"):
        op.add_column("users", sa.Column("notes", sa.Text(), nullable=True))
    if not _has_column("users", "updated_at"):
        op.add_column("users", sa.Column("updated_at", sa.DateTime(), nullable=True))
        op.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")

    op.execute(
        "UPDATE users SET role = 'owner_admin' "
        "WHERE email = 'demo@sovereign.studio' AND role = 'family_user'"
    )


def downgrade() -> None:
    if _has_column("users", "updated_at"):
        op.drop_column("users", "updated_at")
    if _has_column("users", "notes"):
        op.drop_column("users", "notes")
    if _has_column("users", "status"):
        op.drop_column("users", "status")
    if _has_column("users", "role"):
        op.drop_column("users", "role")
