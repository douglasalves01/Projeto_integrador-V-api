import sys

from loguru import logger

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    logger.remove()

    log_level = "DEBUG" if settings.DEBUG else "INFO"

    logger.add(
        sys.stdout,
        level=log_level,
        serialize=True,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
    )
