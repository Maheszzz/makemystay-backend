"""add_status_and_error_to_sync_metadata

Revision ID: a9ef570c46f0
Revises: db9cc1a1587d
Create Date: 2026-03-12 12:40:30.707287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9ef570c46f0'
down_revision: Union[str, Sequence[str], None] = 'db9cc1a1587d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('sync_metadata', sa.Column('status', sa.String(length=20), nullable=True, server_default='active'))
    op.add_column('sync_metadata', sa.Column('last_error', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sync_metadata', 'last_error')
    op.drop_column('sync_metadata', 'status')
