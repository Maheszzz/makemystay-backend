"""add_crm_retry_count_to_leads

Revision ID: 7e87738469e8
Revises: f8a9b0c1d2e3
Create Date: 2026-04-14 17:03:00.871555

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '7e87738469e8'
down_revision: Union[str, Sequence[str], None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def _column_exists(bind, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspect(bind).get_columns(table))


def _index_names(bind, table: str) -> set[str]:
    return {i["name"] for i in inspect(bind).get_indexes(table) if i.get("name")}


def _safe_create_index(
    bind,
    name: str,
    table: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if name not in _index_names(bind, table):
        op.create_index(name, table, columns, unique=unique)


def _safe_drop_index(bind, name: str, table: str) -> None:
    if name in _index_names(bind, table):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # zoho_webhook_events may already exist (manual / partial run) — avoid 1050 duplicate table.
    if not _table_exists(bind, "zoho_webhook_events"):
        op.create_table(
            "zoho_webhook_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("event_id", sa.String(length=100), nullable=False),
            sa.Column("event_type", sa.String(length=50), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=True),
            sa.Column("processing_time_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("error_log", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    _safe_create_index(
        bind, op.f("ix_zoho_webhook_events_event_id"), "zoho_webhook_events", ["event_id"], unique=True
    )
    _safe_create_index(
        bind, op.f("ix_zoho_webhook_events_event_type"), "zoho_webhook_events", ["event_type"], unique=False
    )
    _safe_create_index(bind, op.f("ix_zoho_webhook_events_id"), "zoho_webhook_events", ["id"], unique=False)
    _safe_create_index(bind, op.f("ix_zoho_webhook_events_source"), "zoho_webhook_events", ["source"], unique=False)
    _safe_create_index(bind, op.f("ix_zoho_webhook_events_status"), "zoho_webhook_events", ["status"], unique=False)
    _safe_create_index(
        bind, "ix_zoho_webhook_events_status_created", "zoho_webhook_events", ["status", "created_at"], unique=False
    )

    if not _column_exists(bind, "contacts", "source"):
        op.add_column("contacts", sa.Column("source", sa.String(length=100), nullable=True))

    _safe_create_index(bind, op.f("ix_failed_zoho_tasks_id"), "failed_zoho_tasks", ["id"], unique=False)

    if not _column_exists(bind, "leads", "crm_retry_count"):
        op.add_column("leads", sa.Column("crm_retry_count", sa.Integer(), nullable=True))
        op.execute(sa.text("UPDATE leads SET crm_retry_count = 0 WHERE crm_retry_count IS NULL"))
        op.alter_column(
            "leads",
            "crm_retry_count",
            existing_type=mysql.INTEGER(),
            nullable=False,
        )

    op.alter_column(
        "leads",
        "lead_stage",
        existing_type=mysql.VARCHAR(length=50),
        nullable=False,
        existing_server_default=sa.text("'new'"),
    )
    op.alter_column(
        "leads",
        "inquiry_count",
        existing_type=mysql.INTEGER(),
        nullable=False,
        existing_server_default=sa.text("'1'"),
    )
    op.alter_column(
        "leads",
        "reentry_count",
        existing_type=mysql.INTEGER(),
        nullable=False,
        existing_server_default=sa.text("'0'"),
    )
    _safe_drop_index(bind, "ix_leads_phone_unique", "leads")
    _safe_drop_index(bind, "uq_normalized_phone", "leads")
    _safe_create_index(bind, "idx_phone_stage", "leads", ["normalized_phone", "lead_stage"], unique=False)
    _safe_create_index(bind, "ix_leads_crm_status_retry", "leads", ["crm_status", "crm_retry_count"], unique=False)
    _safe_create_index(bind, op.f("ix_leads_last_activity_at"), "leads", ["last_activity_at"], unique=False)
    _safe_create_index(bind, op.f("ix_leads_normalized_phone"), "leads", ["normalized_phone"], unique=True)
    _safe_create_index(bind, "unique_normalized_phone", "leads", ["normalized_phone"], unique=True)
    op.alter_column(
        "properties",
        "location",
        existing_type=mysql.VARCHAR(length=150),
        nullable=True,
    )
    op.alter_column(
        "properties",
        "phone",
        existing_type=mysql.VARCHAR(length=15),
        nullable=True,
    )
    op.alter_column(
        "properties",
        "property_type",
        existing_type=mysql.VARCHAR(length=50),
        nullable=True,
    )
    _safe_drop_index(bind, "ix_properties_avg_rating", "properties")
    _safe_drop_index(bind, "ix_properties_created_at", "properties")
    _safe_drop_index(bind, "ix_properties_deleted_listing_type", "properties")
    _safe_drop_index(bind, "ix_properties_starting_price", "properties")
    _safe_drop_index(bind, "idx_property", "property_images")
    _safe_drop_index(bind, "ix_property_images_prop_deleted_sort", "property_images")


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index('ix_property_images_prop_deleted_sort', 'property_images', ['property_id', 'is_deleted', 'sort_order'], unique=False)
    op.create_index('idx_property', 'property_images', ['property_id'], unique=False)
    op.create_index('ix_properties_starting_price', 'properties', ['starting_price'], unique=False)
    op.create_index('ix_properties_deleted_listing_type', 'properties', ['is_deleted', 'listing_type'], unique=False)
    op.create_index('ix_properties_created_at', 'properties', ['created_at'], unique=False)
    op.create_index('ix_properties_avg_rating', 'properties', ['avg_rating'], unique=False)
    op.alter_column('properties', 'property_type',
               existing_type=mysql.VARCHAR(length=50),
               nullable=False)
    op.alter_column('properties', 'phone',
               existing_type=mysql.VARCHAR(length=15),
               nullable=False)
    op.alter_column('properties', 'location',
               existing_type=mysql.VARCHAR(length=150),
               nullable=False)
    op.drop_index('unique_normalized_phone', table_name='leads')
    op.drop_index(op.f('ix_leads_normalized_phone'), table_name='leads')
    op.drop_index(op.f('ix_leads_last_activity_at'), table_name='leads')
    op.drop_index('ix_leads_crm_status_retry', table_name='leads')
    op.drop_index('idx_phone_stage', table_name='leads')
    op.create_index('uq_normalized_phone', 'leads', ['normalized_phone'], unique=True)
    op.create_index('ix_leads_phone_unique', 'leads', ['phone'], unique=True)
    op.alter_column('leads', 'reentry_count',
               existing_type=mysql.INTEGER(),
               nullable=True,
               existing_server_default=sa.text("'0'"))
    op.alter_column('leads', 'inquiry_count',
               existing_type=mysql.INTEGER(),
               nullable=True,
               existing_server_default=sa.text("'1'"))
    op.alter_column('leads', 'lead_stage',
               existing_type=mysql.VARCHAR(length=50),
               nullable=True,
               existing_server_default=sa.text("'new'"))
    op.drop_column('leads', 'crm_retry_count')
    op.drop_index(op.f('ix_failed_zoho_tasks_id'), table_name='failed_zoho_tasks')
    op.drop_column('contacts', 'source')
    op.drop_index('ix_zoho_webhook_events_status_created', table_name='zoho_webhook_events')
    op.drop_index(op.f('ix_zoho_webhook_events_status'), table_name='zoho_webhook_events')
    op.drop_index(op.f('ix_zoho_webhook_events_source'), table_name='zoho_webhook_events')
    op.drop_index(op.f('ix_zoho_webhook_events_id'), table_name='zoho_webhook_events')
    op.drop_index(op.f('ix_zoho_webhook_events_event_type'), table_name='zoho_webhook_events')
    op.drop_index(op.f('ix_zoho_webhook_events_event_id'), table_name='zoho_webhook_events')
    op.drop_table('zoho_webhook_events')
    # ### end Alembic commands ###
