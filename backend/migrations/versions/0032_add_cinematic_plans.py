"""Persist reviewed cinematic plans separately from presenter movies."""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    if "cinematic_plans" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "cinematic_plans",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cinematic_plans_user_id", "cinematic_plans", ["user_id"])


def downgrade():
    if "cinematic_plans" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("cinematic_plans")
