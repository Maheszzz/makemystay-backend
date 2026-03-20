"""add_recovery_sent_to_payments

Revision ID: e10be14f9da7
Revises: f4a1c9b2e8d7
Create Date: 2026-03-20 22:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e10be14f9da7'
down_revision: Union[str, None] = 'f4a1c9b2e8d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add recovery_sent column to payments table
    op.add_column('payments', sa.Column('recovery_sent', sa.Boolean(), server_default=sa.text('0'), nullable=False))


def downgrade() -> None:
    # Remove recovery_sent column from payments table
    op.drop_column('payments', 'recovery_sent')
