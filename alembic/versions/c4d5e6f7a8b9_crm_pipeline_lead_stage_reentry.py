"""CRM pipeline: lead_stage, last_contacted_at, reentry_count

Revision ID: c4d5e6f7a8b9
Revises: 16293c6e4d57
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "16293c6e4d57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    """Skip ADD COLUMN when the column already exists."""
    bind = op.get_bind()
    r = bind.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table_name, "c": column_name},
    )
    return (r.scalar() or 0) > 0


def _mysql_index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    ix = str(index_name)
    r = bind.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND INDEX_NAME = :ix"
        ),
        {"t": table_name, "ix": ix},
    )
    return (r.scalar() or 0) > 0


def upgrade() -> None:
    if not _mysql_column_exists("leads", "lead_stage"):
        op.add_column(
            "leads",
            sa.Column(
                "lead_stage",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'new'"),
            ),
        )
    if not _mysql_column_exists("leads", "last_contacted_at"):
        op.add_column(
            "leads",
            sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _mysql_column_exists("leads", "reentry_count"):
        op.add_column(
            "leads",
            sa.Column(
                "reentry_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if not _mysql_index_exists("leads", "ix_leads_lead_stage"):
        op.create_index(op.f("ix_leads_lead_stage"), "leads", ["lead_stage"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_leads_lead_stage"), table_name="leads")
    op.drop_column("leads", "reentry_count")
    op.drop_column("leads", "last_contacted_at")
    op.drop_column("leads", "lead_stage")
