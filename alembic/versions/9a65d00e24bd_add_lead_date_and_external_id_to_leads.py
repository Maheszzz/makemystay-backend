"""add_lead_date_and_external_id_to_leads

Revision ID: 9a65d00e24bd
Revises: 80135b929687
Create Date: 2026-03-12 11:55:18.741720

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a65d00e24bd'
down_revision: Union[str, Sequence[str], None] = '80135b929687'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only add columns to leads table
    op.add_column('leads', sa.Column('lead_date', sa.Integer(), nullable=True))
    op.add_column('leads', sa.Column('external_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_leads_external_id'), 'leads', ['external_id'], unique=False)
    op.create_index(op.f('ix_leads_lead_date'), 'leads', ['lead_date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_leads_lead_date'), table_name='leads')
    op.drop_index(op.f('ix_leads_external_id'), table_name='leads')
    op.drop_column('leads', 'external_id')
    op.drop_column('leads', 'lead_date')
