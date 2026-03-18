from loguru import logger

from app.core.config import settings

# Map environment strings to valid Loguru levels
env_level = settings.ENV.upper()
if env_level in ["LOCAL", "DEVELOPMENT", "DEV"]:
    LOG_LEVEL = "DEBUG"
elif env_level in ["PRODUCTION", "PROD"]:
    LOG_LEVEL = "INFO"
else:
    LOG_LEVEL = "INFO"

# Set up logging configuration
def setup_logger():
    logger.remove()  # Remove default logger
    logger.add(
        "app/logs/app_{time:YYYY-MM-DD}.log",
        level=LOG_LEVEL,
        rotation="1 day",  # Rotate log daily
        retention="7 days",  # Keep logs for 7 days
        compression="zip",  # Compress old logs
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message} | {extra}",
    )
    logger.add(
        "app/logs/app_error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message} | {extra}",
    )


setup_logger()
