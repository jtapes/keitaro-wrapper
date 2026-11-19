"""campaign_log

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("keitaro_campaign_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("geo", sa.String(2), nullable=False, server_default=""),
        sa.Column("offer_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaign_log_keitaro_campaign_id", "campaign_log", ["keitaro_campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_log_keitaro_campaign_id", table_name="campaign_log")
    op.drop_table("campaign_log")
