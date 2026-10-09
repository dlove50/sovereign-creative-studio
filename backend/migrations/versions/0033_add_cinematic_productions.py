"""Revision-scoped cinematic shot links and assembly state."""
from alembic import op
import sqlalchemy as sa
revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

def upgrade():
    if "cinematic_productions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table("cinematic_productions",
        sa.Column("plan_id", sa.String(32), sa.ForeignKey("cinematic_plans.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("result_url", sa.String(512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True))

def downgrade():
    if "cinematic_productions" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("cinematic_productions")
