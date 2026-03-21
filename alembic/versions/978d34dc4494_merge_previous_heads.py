"""Merge previous heads

Revision ID: 978d34dc4494
Revises: a1b2c3d4e5f6, c3f1a2b4d5e6
Create Date: 2026-03-21 11:03:24.921961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '978d34dc4494'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'c3f1a2b4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
