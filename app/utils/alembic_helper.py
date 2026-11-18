from loguru import logger
from app.core.config import load_app_env


def load_alembic_env():
    """
    Load environment variables for Alembic using the centralized app.core.config loader.
    """
    env_files = load_app_env()
    logger.info(f"Alembic: Centralized environment loader configured ({', '.join(env_files)})")
