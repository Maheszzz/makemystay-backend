"""add_assignment_batches_table

Revision ID: 874a5a48fc28
Revises: 15c6e830bc43
Create Date: 2026-03-23 23:16:00.965474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '874a5a48fc28'
down_revision: Union[str, Sequence[str], None] = '15c6e830bc43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('assignment_batches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('total_leads', sa.Integer(), nullable=False),
        sa.Column('rm_count', sa.Integer(), nullable=False),
        sa.Column('strategy', sa.Enum('round_robin', 'load_balanced', 'manual_bulk', name='assign_strategy_enum'), nullable=False),
        sa.Column('distribution', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_assignment_batches_id'), 'assignment_batches', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_assignment_batches_id'), table_name='assignment_batches')
    op.drop_table('assignment_batches')
