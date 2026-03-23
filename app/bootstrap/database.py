"""
Database side-effects at startup.

Production: schema changes go through **Alembic** (`alembic upgrade head`).
Optional `SQLALCHEMY_CREATE_ALL_ON_STARTUP` is for local dev / empty DB only.
"""

from __future__ import annotations

from loguru import logger

from app.configs.db_config import MySQLBase, mysql_engine
from app.core.config import settings


def import_mysql_models() -> None:
    """Import all model modules so SQLAlchemy registers tables on MySQLBase.metadata."""
    # noqa: F401 — side effect: populate metadata
    from app.models import (
        agent,
        assignment_batch,
        booking,
        demo,
        failed_job,
        lead,
        lead_activity,
        lead_assignment,
        lead_event,
        ledger,
        payment,
        payment_webhook_event,
        realty,
        reconciliation,
        retell_call,
        sync_job,
        sync_metadata,
        user,
    )


def maybe_create_tables_from_metadata() -> None:
    """
    Call SQLAlchemy create_all only when explicitly enabled.

    In production, rely on Alembic migrations. Enable for local dev via:
        SQLALCHEMY_CREATE_ALL_ON_STARTUP=true
    """
    if not getattr(settings, "SQLALCHEMY_CREATE_ALL_ON_STARTUP", False):
        logger.info("SQLAlchemy create_all skipped (use Alembic). Set SQLALCHEMY_CREATE_ALL_ON_STARTUP=true for dev-only DDL.")
        return
    import_mysql_models()
    MySQLBase.metadata.create_all(bind=mysql_engine)
    logger.warning("SQLAlchemy create_all ran — intended for development only.")
