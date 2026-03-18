# MySQL Configuration for Realty Database
# Build connection URL from individual environment variables
import os
import urllib.parse

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.configs.log_config import setup_logger

setup_logger()
load_dotenv()


from app.core.config import settings
from app.core.logger import logger

# MySQL Configuration for Realty Database
# Build connection URL from individual environment variables

DB_USER = settings.DB_USER
DB_PASSWORD = settings.DB_PASSWORD
DB_HOST = settings.DB_HOST
DB_PORT = settings.DB_PORT
DB_NAME = settings.DB_NAME

# URL encode the password to handle special characters like @, #, etc.
encoded_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""

MYSQL_DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

logger.info(f"Creating MySQL engine for {DB_HOST}:{DB_PORT}/{DB_NAME}")
mysql_engine = create_engine(
    MYSQL_DATABASE_URL, 
    echo=True, 
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30
)

logger.info("Creating MySQL session local")
MySQLSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mysql_engine)

logger.info("Creating MySQL declarative base")
MySQLBase = declarative_base()


def get_mysql_db():
    db = MySQLSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Make MySQL the default database for existing code compatibility
SessionLocal = MySQLSessionLocal
Base = MySQLBase
get_db = get_mysql_db

# Stub for get_async_db (not used with MySQL, but needed for imports)
