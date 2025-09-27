from __future__ import annotations

import logging
from typing import Optional

from .config import settings


def configure_logging(level: Optional[str] = None, log_path: Optional[str] = None) -> None:
    log_level = getattr(logging, (level or settings.log_level).upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path:
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        handlers=handlers,
    )


def get_logger(name: str) -> logging.Logger:
    if not logging.getLogger().handlers:
        configure_logging(settings.log_level, settings.log_path.as_posix() if settings.log_path else None)
    return logging.getLogger(name)
