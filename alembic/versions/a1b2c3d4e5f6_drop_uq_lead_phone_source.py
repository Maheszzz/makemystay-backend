"""drop uq_lead_phone_source constraint

The UNIQUE(phone, source) constraint incorrectly blocked customers from
making more than one inquiry per lead source (e.g. Housing.com). Any second
enquiry from the same phone number was silently discarded as an IntegrityError.

The correct deduplication is handled at the application layer using
external_id, lead_date, and phone together (uq_lead_phone_date_ext).

Revision ID: a1b2c3d4e5f6
Revises: db9cc1a1587d
Create Date: 2026-03-20 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e10be14f9da7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the over-restrictive phone+source unique constraint (if it exists)."""
    from alembic import op as _op
    from sqlalchemy import text
    bind = _op.get_bind()
    result = bind.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'leads' "
            "AND CONSTRAINT_NAME = 'uq_lead_phone_source'"
        )
    )
    if result.scalar() > 0:
        op.drop_constraint('uq_lead_phone_source', 'leads', type_='unique')


def downgrade() -> None:
    """Re-add the constraint (not recommended — this blocks multi-property leads)."""
    op.create_unique_constraint('uq_lead_phone_source', 'leads', ['phone', 'source'])
