"""
AITBC Logging Module
Centralized logging utilities for the AITBC project
"""

import json
import logging
import logging.handlers
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


class BlockchainTextFormatter(logging.Formatter):
    """Compact bracketed formatter that appends blockchain-specific extra fields."""

    BLOCKCHAIN_FIELDS = ("chain_id", "supported_chains", "height", "hash", "proposer", "error", "request_id", "node_id")

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        extra_fields = [f"{f}={getattr(record, f)}" for f in self.BLOCKCHAIN_FIELDS if hasattr(record, f)]
        if extra_fields:
            message = f"{message} [{', '.join(extra_fields)}]"
        return f"[{record.levelname}] {message}"


class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for log aggregation"""

    BLOCKCHAIN_FIELDS = (
        "chain_id",
        "supported_chains",
        "height",
        "hash",
        "proposer",
        "error",
        "request_id",
        "node_id",
        "service",
        "environment",
        "version",
    )

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON"""
        log_entry = {
            "timestamp": f"{datetime.utcnow().isoformat()}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add standard fields
        for f in self.BLOCKCHAIN_FIELDS:
            if hasattr(record, f):
                log_entry[f] = getattr(record, f)

        # Add extra fields if present
        if hasattr(record, "extra"):
            log_entry.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def _get_log_level() -> int:
    """Get log level from environment"""
    return getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper())  # type: ignore[no-any-return]


def _get_log_format() -> str:
    """Get log format from environment: 'json' or 'text'"""
    return os.getenv("LOG_FORMAT", "text").lower()


def _get_log_file_path(service_name: str) -> Path | None:
    """Get log file path from environment"""
    log_dir = os.getenv("LOG_DIR")
    if not log_dir:
        return None
    log_path = Path(log_dir) / service_name
    log_path.mkdir(parents=True, exist_ok=True)
    return log_path / f"{service_name}.log"


def setup_logger(
    name: str,
    level: str = "INFO",
    format_string: str | None = None,
    structured: bool = False,
    service_name: str | None = None,
    to_file: bool = False,
    rotation: str = "daily",
    max_files: int = 7,
) -> logging.Logger:
    """Setup a logger with consistent formatting and optional file rotation"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)

        if structured or _get_log_format() == "json":
            formatter: logging.Formatter = StructuredFormatter()
        else:
            if format_string is None:
                format_string = "[%(levelname)s] %(message)s"
            formatter = logging.Formatter(format_string)

        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler with rotation
        if to_file and service_name:
            log_file = _get_log_file_path(service_name)
            if log_file:
                file_handler: logging.Handler
                if rotation == "daily":
                    file_handler = logging.handlers.TimedRotatingFileHandler(
                        log_file, when="midnight", interval=1, backupCount=max_files, encoding="utf-8"
                    )
                elif rotation == "size":
                    file_handler = logging.handlers.RotatingFileHandler(
                        log_file, maxBytes=10 * 1024 * 1024, backupCount=max_files, encoding="utf-8"
                    )
                else:
                    file_handler = logging.FileHandler(log_file, encoding="utf-8")

                file_handler.setFormatter(StructuredFormatter())
                logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)


def get_blockchain_logger(name: str) -> logging.Logger:
    """Get a logger with blockchain-specific extra field formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        level = _get_log_level()
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(BlockchainTextFormatter())
        logger.addHandler(handler)
    return logger


def configure_logging(
    level: str = "INFO",
    structured: bool = False,
    service_name: str | None = None,
    to_file: bool = False,
) -> None:
    """Configure root logging level and format"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers for clean configuration
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if structured or _get_log_format() == "json":
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root_logger.addHandler(console_handler)

    # File handler with rotation
    if to_file and service_name:
        log_file = _get_log_file_path(service_name)
        if log_file:
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
            )
            file_handler.setFormatter(StructuredFormatter())
            root_logger.addHandler(file_handler)


@contextmanager
def log_context(**kwargs: Any) -> Any:
    """Context manager for adding contextual information to logs"""
    logger = logging.getLogger()

    class ContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            for key, value in kwargs.items():
                setattr(record, key, value)
            return True

    context_filter = ContextFilter()
    logger.addFilter(context_filter)
    try:
        yield
    finally:
        logger.removeFilter(context_filter)


class LogContext:
    """Class for adding contextual information to logs across multiple calls"""

    def __init__(self, **kwargs: Any) -> None:
        self.context = kwargs

    def __enter__(self) -> Any:
        return log_context(**self.context).__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass
