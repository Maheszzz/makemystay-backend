"""add_composite_unique_constraint_to_leads

Revision ID: db9cc1a1587d
Revises: 9a65d00e24bd
Create Date: 2026-03-12 12:35:48.123456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db9cc1a1587d'
down_revision: Union[str, Sequence[str], None] = '9a65d00e24bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only add the unique constraint to leads table
    op.create_unique_constraint('uq_lead_phone_date_ext', 'leads', ['phone', 'lead_date', 'external_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_lead_phone_date_ext', 'leads', type_='unique')
