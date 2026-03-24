"""add_contact_columns

Revision ID: cd61ded70119
Revises: 874a5a48fc28
Create Date: 2026-03-24 09:54:26.510956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd61ded70119'
down_revision: Union[str, Sequence[str], None] = '874a5a48fc28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('contacts', sa.Column('is_ai_called', sa.Boolean(), server_default='0', nullable=True))
    op.add_column('contacts', sa.Column('call_status', sa.String(length=50), nullable=True))
    op.add_column('contacts', sa.Column('interested', sa.Boolean(), nullable=True))
    op.add_column('contacts', sa.Column('budget', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('contacts', 'budget')
    op.drop_column('contacts', 'interested')
    op.drop_column('contacts', 'call_status')
    op.drop_column('contacts', 'is_ai_called')
