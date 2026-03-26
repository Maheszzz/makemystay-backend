"""add zoho_user_id to employees

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-25 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('employees', sa.Column('zoho_user_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_employees_zoho_user_id'), 'employees', ['zoho_user_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_employees_zoho_user_id'), table_name='employees')
    op.drop_column('employees', 'zoho_user_id')
