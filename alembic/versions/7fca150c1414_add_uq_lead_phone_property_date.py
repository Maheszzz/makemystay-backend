"""add_uq_lead_phone_property_date

Revision ID: 7fca150c1414
Revises: 978d34dc4494
Create Date: 2026-03-21 11:03:33.728844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fca150c1414'
down_revision: Union[str, Sequence[str], None] = '978d34dc4494'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint("uq_lead_phone_property_date", "leads", ["phone", "property_id", "lead_date"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_lead_phone_property_date", "leads", type_="unique")
