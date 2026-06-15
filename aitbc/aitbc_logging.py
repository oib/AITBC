"""
AITBC Logging Module
Centralized logging utilities for the AITBC project
"""

import json
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Any


class BlockchainTextFormatter(logging.Formatter):
    """Compact bracketed formatter that appends blockchain-specific extra fields."""

    BLOCKCHAIN_FIELDS = ("chain_id", "supported_chains", "height", "hash", "proposer", "error")

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        extra_fields = [f"{f}={getattr(record, f)}" for f in self.BLOCKCHAIN_FIELDS if hasattr(record, f)]
        if extra_fields:
            message = f"{message} [{', '.join(extra_fields)}]"
        return f"[{record.levelname}] {message}"


class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for log aggregation"""

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

        # Add extra fields if present
        if hasattr(record, "extra"):
            log_entry.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logger(name: str, level: str = "INFO", format_string: str | None = None, structured: bool = False) -> logging.Logger:
    """Setup a logger with consistent formatting"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)

        if structured:
            formatter: logging.Formatter = StructuredFormatter()
        else:
            if format_string is None:
                format_string = "[%(levelname)s] %(message)s"
            formatter = logging.Formatter(format_string)

        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)


def get_blockchain_logger(name: str) -> logging.Logger:
    """Get a logger with blockchain-specific extra field formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        level = logging.getLevelName(os.getenv("LOG_LEVEL", "INFO").upper())
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(BlockchainTextFormatter())
        logger.addHandler(handler)
    return logger


def configure_logging(level: str = "INFO", structured: bool = False) -> None:
    """Configure root logging level"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    if structured:
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add structured handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(handler)
    else:
        # Ensure root logger has a handler with compact bracketed format
        if not root_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            root_logger.addHandler(handler)


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
