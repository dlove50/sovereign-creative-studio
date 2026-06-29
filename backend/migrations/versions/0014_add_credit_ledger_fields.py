"""add credit ledger metadata fields

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_column("credit_transactions", "transaction_type"):
        op.add_column(
            "credit_transactions",
            sa.Column(
                "transaction_type",
                sa.String(length=32),
                nullable=False,
                server_default="generation_charge",
            ),
        )
    if not _has_column("credit_transactions", "related_feature"):
        op.add_column(
            "credit_transactions",
            sa.Column(
                "related_feature",
                sa.String(length=40),
                nullable=False,
                server_default="base_generation",
            ),
        )
    if not _has_column("credit_transactions", "related_id"):
        op.add_column(
            "credit_transactions",
            sa.Column("related_id", sa.String(length=32), nullable=True),
        )
        op.create_index(
            "ix_credit_transactions_related_id",
            "credit_transactions",
            ["related_id"],
        )
    if not _has_column("credit_transactions", "status"):
        op.add_column(
            "credit_transactions",
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="completed",
            ),
        )
    if not _has_column("credit_transactions", "note"):
        op.add_column("credit_transactions", sa.Column("note", sa.Text(), nullable=True))

    op.execute(
        "UPDATE credit_transactions "
        "SET related_id = generation_id "
        "WHERE related_id IS NULL AND generation_id IS NOT NULL"
    )
    op.execute(
        "UPDATE credit_transactions "
        "SET note = reason "
        "WHERE note IS NULL AND reason IS NOT NULL"
    )


def downgrade() -> None:
    if _has_column("credit_transactions", "note"):
        op.drop_column("credit_transactions", "note")
    if _has_column("credit_transactions", "status"):
        op.drop_column("credit_transactions", "status")
    if _has_column("credit_transactions", "related_id"):
        op.drop_index("ix_credit_transactions_related_id", table_name="credit_transactions")
        op.drop_column("credit_transactions", "related_id")
    if _has_column("credit_transactions", "related_feature"):
        op.drop_column("credit_transactions", "related_feature")
    if _has_column("credit_transactions", "transaction_type"):
        op.drop_column("credit_transactions", "transaction_type")
