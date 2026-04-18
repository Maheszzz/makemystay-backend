import sys
from pathlib import Path
from loguru import logger
from app.core.config import settings

env_level = settings.ENV.upper()
if env_level in ["LOCAL", "DEVELOPMENT", "DEV"]:
    LOG_LEVEL = "DEBUG"
elif env_level in ["PRODUCTION", "PROD"]:
    LOG_LEVEL = "INFO"
else:
    LOG_LEVEL = "INFO"

_LOG_FMT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message} | {extra}"

def setup_logger() -> None:
    logger.remove()
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_dir / "app_{time:YYYY-MM-DD}.log"),
            level=LOG_LEVEL,
            rotation="1 day",
            retention="7 days",
            compression="zip",
            format=_LOG_FMT,
        )
        logger.add(
            str(log_dir / "app_error_{time:YYYY-MM-DD}.log"),
            level="ERROR",
            rotation="1 day",
            retention="7 days",
            compression="zip",
            format=_LOG_FMT,
        )
    except OSError:
        logger.add(sys.stderr, level=LOG_LEVEL, format=_LOG_FMT)

setup_logger()
