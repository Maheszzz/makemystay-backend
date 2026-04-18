"""add city to properties

Revision ID: a73d8822d1bc
Revises: 7e87738469e8
Create Date: 2026-04-18 14:48:15.003449

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a73d8822d1bc'
down_revision: Union[str, Sequence[str], None] = '7e87738469e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add city column to properties table."""
    op.add_column('properties', sa.Column('city', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_properties_city'), 'properties', ['city'], unique=False)


def downgrade() -> None:
    """Remove city column and index from properties table."""
    op.drop_index(op.f('ix_properties_city'), table_name='properties')
    op.drop_column('properties', 'city')
