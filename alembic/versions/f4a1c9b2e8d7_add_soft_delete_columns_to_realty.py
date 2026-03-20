"""add_soft_delete_columns_to_realty

Revision ID: f4a1c9b2e8d7
Revises: d2d3b0fbd32c
Create Date: 2026-03-20 12:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a1c9b2e8d7"
down_revision: Union[str, Sequence[str], None] = "d2d3b0fbd32c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    properties_columns = {col["name"] for col in inspector.get_columns("properties")}
    if "is_deleted" not in properties_columns:
        op.add_column(
            "properties",
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    property_images_columns = {
        col["name"] for col in inspector.get_columns("property_images")
    }
    if "is_deleted" not in property_images_columns:
        op.add_column(
            "property_images",
            sa.Column(
                "is_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    property_images_columns = {
        col["name"] for col in inspector.get_columns("property_images")
    }
    if "is_deleted" in property_images_columns:
        op.drop_column("property_images", "is_deleted")

    properties_columns = {col["name"] for col in inspector.get_columns("properties")}
    if "is_deleted" in properties_columns:
        op.drop_column("properties", "is_deleted")
