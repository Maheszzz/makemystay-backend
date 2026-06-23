"""Add onboarding fields to properties

Revision ID: h5i6j7k8l9m1
Revises: h4i5j6k7l9m0
Create Date: 2026-06-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h5i6j7k8l9m1"
down_revision: Union[str, Sequence[str], None] = "066f9f761333"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    pcols = _col_names(inspector, "properties")
    if "property_code" not in pcols:
        op.add_column("properties", sa.Column("property_code", sa.String(50), nullable=True))
        op.create_index(op.f("ix_properties_property_code"), "properties", ["property_code"], unique=True)
    if "gender_preference" not in pcols:
        op.add_column("properties", sa.Column("gender_preference", sa.String(50), nullable=True))
    if "property_category" not in pcols:
        op.add_column("properties", sa.Column("property_category", sa.String(100), nullable=True))
    if "locality" not in pcols:
        op.add_column("properties", sa.Column("locality", sa.String(150), nullable=True))
        op.create_index(op.f("ix_properties_locality"), "properties", ["locality"], unique=False)
    if "latitude" not in pcols:
        op.add_column("properties", sa.Column("latitude", sa.DECIMAL(10, 8), nullable=True))
    if "longitude" not in pcols:
        op.add_column("properties", sa.Column("longitude", sa.DECIMAL(11, 8), nullable=True))
    if "available_beds" not in pcols:
        op.add_column("properties", sa.Column("available_beds", sa.Integer(), nullable=True))
    if "metadata" not in pcols:
        op.add_column("properties", sa.Column("metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    try:
        op.drop_index(op.f("ix_properties_locality"), table_name="properties")
    except Exception:
        pass
    try:
        op.drop_index(op.f("ix_properties_property_code"), table_name="properties")
    except Exception:
        pass
        
    for col in (
        "metadata",
        "available_beds",
        "longitude",
        "latitude",
        "locality",
        "property_category",
        "gender_preference",
        "property_code",
    ):
        try:
            op.drop_column("properties", col)
        except Exception:
            pass
