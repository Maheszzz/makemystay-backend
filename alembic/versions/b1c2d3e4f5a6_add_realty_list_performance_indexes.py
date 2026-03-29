"""add indexes for property list queries and image bulk load

Revision ID: b1c2d3e4f5a6
Revises: a0b3c4d5e6f7
Create Date: 2026-03-29 12:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a0b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    props_ix = {i["name"] for i in inspector.get_indexes("properties")}
    if "ix_properties_deleted_listing_type" not in props_ix:
        op.create_index(
            "ix_properties_deleted_listing_type",
            "properties",
            ["is_deleted", "listing_type"],
            unique=False,
        )

    if inspector.has_table("property_images"):
        img_ix = {i["name"] for i in inspector.get_indexes("property_images")}
        if "ix_property_images_prop_deleted_sort" not in img_ix:
            op.create_index(
                "ix_property_images_prop_deleted_sort",
                "property_images",
                ["property_id", "is_deleted", "sort_order"],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("property_images"):
        img_ix = {i["name"] for i in inspector.get_indexes("property_images")}
        if "ix_property_images_prop_deleted_sort" in img_ix:
            op.drop_index("ix_property_images_prop_deleted_sort", table_name="property_images")

    props_ix = {i["name"] for i in inspector.get_indexes("properties")}
    if "ix_properties_deleted_listing_type" in props_ix:
        op.drop_index("ix_properties_deleted_listing_type", table_name="properties")
