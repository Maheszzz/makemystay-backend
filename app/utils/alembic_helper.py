import os
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

def load_alembic_env():
    """
    Explicitly loads environment variables for Alembic.
    Prioritizes .env.production on servers, falls back to .env.
    """
    # Project root is one level up from 'app'
    root_dir = Path(__file__).resolve().parent.parent.parent
    
    env_production = root_dir / ".env.production"
    env_standard = root_dir / ".env"
    
    if env_production.exists():
        logger.info(f"Alembic: Loading production environment from {env_production}")
        load_dotenv(env_production)
    elif env_standard.exists():
        logger.info(f"Alembic: Loading environment from {env_standard}")
        load_dotenv(env_standard)
    else:
        logger.warning("Alembic: No .env or .env.production found at project root.")
