"""add last_zoho_sync_at to leads

Revision ID: 723352ddb5a5
Revises: f24ced3cce34
Create Date: 2026-04-02 12:51:15.558283

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '723352ddb5a5'
down_revision: Union[str, Sequence[str], None] = 'f24ced3cce34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("leads", sa.Column("last_zoho_sync_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("leads", "last_zoho_sync_at")
