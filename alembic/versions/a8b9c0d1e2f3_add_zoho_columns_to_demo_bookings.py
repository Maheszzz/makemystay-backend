"""add zoho_lead_id and last_zoho_sync_at to demo_bookings

Revision ID: a8b9c0d1e2f3
Revises: 723352ddb5a5
Create Date: 2026-04-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "723352ddb5a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("demo_bookings")}

    if "zoho_lead_id" not in cols:
        op.add_column(
            "demo_bookings",
            sa.Column("zoho_lead_id", sa.String(length=255), nullable=True),
        )
    if "last_zoho_sync_at" not in cols:
        op.add_column(
            "demo_bookings",
            sa.Column("last_zoho_sync_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("demo_bookings")}

    if "last_zoho_sync_at" in cols:
        op.drop_column("demo_bookings", "last_zoho_sync_at")
    if "zoho_lead_id" in cols:
        op.drop_column("demo_bookings", "zoho_lead_id")
