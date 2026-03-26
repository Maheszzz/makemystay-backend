"""harden csv_imports and add failures table

Revision ID: 680cea7efa1d
Revises: 8ec4c2256844
Create Date: 2026-03-26 18:37:58.936643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '680cea7efa1d'
down_revision: Union[str, Sequence[str], None] = '8ec4c2256844'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add file_hash to csv_imports
    op.add_column('csv_imports', sa.Column('file_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_csv_imports_file_hash'), 'csv_imports', ['file_hash'], unique=False)
    
    # Update default status to pending
    op.alter_column('csv_imports', 'status',
               existing_type=sa.String(length=32),
               server_default='pending',
               existing_nullable=False)

    # Create csv_import_failures table
    op.create_table(
        'csv_import_failures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('import_id', sa.Integer(), nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=True),
        sa.Column('row_data', sa.JSON(), nullable=False),
        sa.Column('error_message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['import_id'], ['csv_imports.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_csv_import_failures_import_id'), 'csv_import_failures', ['import_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_csv_import_failures_import_id'), table_name='csv_import_failures')
    op.drop_table('csv_import_failures')
    
    op.alter_column('csv_imports', 'status',
               existing_type=sa.String(length=32),
               server_default='processing',
               existing_nullable=False)
               
    op.drop_index(op.f('ix_csv_imports_file_hash'), table_name='csv_imports')
    op.drop_column('csv_imports', 'file_hash')
