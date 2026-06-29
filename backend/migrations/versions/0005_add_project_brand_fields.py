"""add lightweight project brand kit fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = [
    ("brand_name", sa.String(length=160)),
    ("brand_voice", sa.Text()),
    ("target_audience", sa.Text()),
    ("primary_colors", sa.Text()),
    ("style_keywords", sa.Text()),
    ("negative_keywords", sa.Text()),
    ("product_positioning", sa.Text()),
    ("campaign_notes", sa.Text()),
]


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    for name, column_type in _COLUMNS:
        if not _has_column("projects", name):
            op.add_column("projects", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        if _has_column("projects", name):
            op.drop_column("projects", name)
