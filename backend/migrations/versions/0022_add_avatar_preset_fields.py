"""add avatar preset/runtime fields

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    cols = _columns("avatar_jobs")
    additions = {
        "avatar_preset": sa.Column("avatar_preset", sa.String(length=32), nullable=True),
        "avatar_width": sa.Column("avatar_width", sa.Integer(), nullable=True),
        "avatar_height": sa.Column("avatar_height", sa.Integer(), nullable=True),
        "avatar_frames": sa.Column("avatar_frames", sa.Integer(), nullable=True),
        "avatar_steps": sa.Column("avatar_steps", sa.Integer(), nullable=True),
        "avatar_cfg": sa.Column("avatar_cfg", sa.Float(), nullable=True),
        "avatar_runtime_seconds": sa.Column("avatar_runtime_seconds", sa.Float(), nullable=True),
    }
    for name, column in additions.items():
        if name not in cols:
            op.add_column("avatar_jobs", column)


def downgrade() -> None:
    cols = _columns("avatar_jobs")
    for name in (
        "avatar_runtime_seconds",
        "avatar_cfg",
        "avatar_steps",
        "avatar_frames",
        "avatar_height",
        "avatar_width",
        "avatar_preset",
    ):
        if name in cols:
            op.drop_column("avatar_jobs", name)
