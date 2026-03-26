"""failed_webhook_leads dead-letter table for webhook ingestion

Revision ID: g3h4i5j6k7l8
Revises: f2a3b4c5d6e7
Create Date: 2026-03-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g3h4i5j6k7l8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "failed_webhook_leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("external_ref", sa.String(length=200), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("error", sa.String(length=2000), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_failed_webhook_leads_source"), "failed_webhook_leads", ["source"], unique=False)
    op.create_index(op.f("ix_failed_webhook_leads_external_ref"), "failed_webhook_leads", ["external_ref"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_failed_webhook_leads_external_ref"), table_name="failed_webhook_leads")
    op.drop_index(op.f("ix_failed_webhook_leads_source"), table_name="failed_webhook_leads")
    op.drop_table("failed_webhook_leads")
