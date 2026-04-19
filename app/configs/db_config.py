# MySQL Configuration for Realty Database
# Build connection URL from individual environment variables
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
    echo=settings.SQLALCHEMY_ECHO,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40,
    pool_timeout=15,
    # Fail fast instead of hanging on unreachable/slow DB.
    # This helps the API return an error quickly (before frontend's 30-45s timeout).
    connect_args={
        "connect_timeout": 5,
        # PyMySQL: avoid half-open connections (Docker / port-forward / flaky networks).
        "read_timeout": 30,
        "write_timeout": 30,
    },
    # Recycle before common wait_timeout / proxy idle limits (stale pooled connections).
    pool_recycle=300,
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
