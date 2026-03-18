import sys

from loguru import logger

# Remove default handler
logger.remove()

# Add console handler
logger.add(sys.stderr, level="INFO")

# Add file handler
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="INFO",
)
