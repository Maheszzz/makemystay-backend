"""add_lead_activities_and_follow_up_at

Revision ID: 15c6e830bc43
Revises: 963896b67d25
Create Date: 2026-03-23 22:47:00.275491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15c6e830bc43'
down_revision: Union[str, Sequence[str], None] = '963896b67d25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('lead_activities',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lead_activities_created_at'), 'lead_activities', ['created_at'], unique=False)
    op.create_index(op.f('ix_lead_activities_id'), 'lead_activities', ['id'], unique=False)
    op.create_index(op.f('ix_lead_activities_lead_id'), 'lead_activities', ['lead_id'], unique=False)
    op.create_index(op.f('ix_lead_activities_type'), 'lead_activities', ['type'], unique=False)

    op.add_column('leads', sa.Column('follow_up_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_leads_follow_up_at'), 'leads', ['follow_up_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_leads_follow_up_at'), table_name='leads')
    op.drop_column('leads', 'follow_up_at')

    op.drop_index(op.f('ix_lead_activities_type'), table_name='lead_activities')
    op.drop_index(op.f('ix_lead_activities_lead_id'), table_name='lead_activities')
    op.drop_index(op.f('ix_lead_activities_id'), table_name='lead_activities')
    op.drop_index(op.f('ix_lead_activities_created_at'), table_name='lead_activities')
    op.drop_table('lead_activities')
