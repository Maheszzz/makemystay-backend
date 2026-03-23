"""
Application bootstrap: router registration and optional DB DDL.

Keep `main.py` thin — wire FastAPI here, not business logic.
"""

from app.bootstrap.database import import_mysql_models, maybe_create_tables_from_metadata
from app.bootstrap.routers import register_routers

__all__ = [
    "import_mysql_models",
    "maybe_create_tables_from_metadata",
    "register_routers",
]
