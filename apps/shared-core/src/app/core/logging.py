"""Shared logging configuration for AITBC services."""

import logging
import sys
from pathlib import Path
from typing import Optional

from ..core.config import ServiceSettings


def setup_logging(settings: Optional[ServiceSettings] = None, level: str = None) -> logging.Logger:
    """Configure structured logging for the service.

    Args:
        settings: Service settings containing log configuration
        level: Override log level

    Returns:
        Configured root logger
    """
    if settings:
        log_level = level or settings.log_level
        log_dir = Path(settings.log_dir)
    else:
        log_level = level or "INFO"
        log_dir = Path("/var/log/aitbc/services")

    log_dir.mkdir(parents=True, exist_ok=True)

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    if settings and settings.service_name:
        file_handler = logging.FileHandler(
            log_dir / f"{settings.service_name}.log"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Usage:
        from aitbc import get_logger
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)