"""add automation toggles to csv_imports

Revision ID: 16293c6e4d57
Revises: bd609251f92e
Create Date: 2026-03-26 19:06:51.037079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '16293c6e4d57'
down_revision: Union[str, Sequence[str], None] = 'bd609251f92e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _mysql_column_exists(table_name: str, column_name: str) -> bool:
    """Skip ADD COLUMN when the column already exists (manual DDL or partial migration)."""
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
    """Upgrade schema."""
    # 1. CsvImport automation toggles
    if not _mysql_column_exists("csv_imports", "sync_to_zoho"):
        op.add_column("csv_imports", sa.Column("sync_to_zoho", sa.Boolean(), nullable=True, server_default=sa.text("1")))
    if not _mysql_column_exists("csv_imports", "send_whatsapp"):
        op.add_column("csv_imports", sa.Column("send_whatsapp", sa.Boolean(), nullable=True, server_default=sa.text("1")))
    if not _mysql_column_exists("csv_imports", "trigger_ai"):
        op.add_column("csv_imports", sa.Column("trigger_ai", sa.Boolean(), nullable=True, server_default=sa.text("1")))

    # 2. Fix missing indices (if any) - avoid dropping idx_property as MySQL FKs need it.
    ix_pi_id = op.f("ix_property_images_id")
    if not _mysql_index_exists("property_images", ix_pi_id):
        op.create_index(ix_pi_id, "property_images", ["id"], unique=False)

    ix_rc_cid = op.f("ix_retell_calls_contact_id")
    if not _mysql_index_exists("retell_calls", ix_rc_cid):
        op.create_index(ix_rc_cid, "retell_calls", ["contact_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    ix_rc_cid = op.f("ix_retell_calls_contact_id")
    if _mysql_index_exists("retell_calls", ix_rc_cid):
        op.drop_index(ix_rc_cid, table_name="retell_calls")

    ix_pi_id = op.f("ix_property_images_id")
    if _mysql_index_exists("property_images", ix_pi_id):
        op.drop_index(ix_pi_id, table_name="property_images")

    if not _mysql_index_exists("property_images", "idx_property"):
        op.create_index("idx_property", "property_images", ["property_id"], unique=False)

    if _mysql_column_exists("csv_imports", "trigger_ai"):
        op.drop_column("csv_imports", "trigger_ai")
    if _mysql_column_exists("csv_imports", "send_whatsapp"):
        op.drop_column("csv_imports", "send_whatsapp")
    if _mysql_column_exists("csv_imports", "sync_to_zoho"):
        op.drop_column("csv_imports", "sync_to_zoho")
