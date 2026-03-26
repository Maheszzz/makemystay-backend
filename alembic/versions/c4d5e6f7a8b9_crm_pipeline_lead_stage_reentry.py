"""CRM pipeline: lead_stage, last_contacted_at, reentry_count

Revision ID: c4d5e6f7a8b9
Revises: 16293c6e4d57
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "16293c6e4d57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "lead_stage",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'new'"),
        ),
    )
    op.add_column(
        "leads",
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "reentry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(op.f("ix_leads_lead_stage"), "leads", ["lead_stage"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_leads_lead_stage"), table_name="leads")
    op.drop_column("leads", "reentry_count")
    op.drop_column("leads", "last_contacted_at")
    op.drop_column("leads", "lead_stage")
