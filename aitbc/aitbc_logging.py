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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JournalFormatter(logging.Formatter):
    """Compact human-readable formatter for systemd journal output.

    Produces clean output like:
        [INFO] [app.main] Starting Coordinator API
        [ERROR] [app.core.lifecycle] Database connection failed

    Tracebacks are not included to avoid multi-line journal spam.
    Use StructuredFormatter (file output) for full traceback capture.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Suppress raw traceback printing by clearing exc_info on the record
        # The exception is already captured in the message via logger.exception()
        record.exc_info = None
        record.exc_text = None
        return f"[{record.levelname}] [{record.name}] {record.getMessage()}"


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
        "correlation_id",
    )

    def __init__(self, include_timestamp: bool = True) -> None:
        """Initialize formatter with optional timestamp inclusion"""
        super().__init__()
        self.include_timestamp = include_timestamp

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON"""
        log_entry = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Only include timestamp if configured (avoid duplicate with systemd journal)
        if self.include_timestamp:
            log_entry["timestamp"] = f"{datetime.now(UTC).isoformat()}Z"

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

        # Console handler - compact human-readable for journal
        console_handler.setFormatter(JournalFormatter())
        logger.addHandler(console_handler)

        # File handler with rotation (JSON format with timestamps for log aggregation)
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

                file_handler.setFormatter(StructuredFormatter(include_timestamp=True))
                logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    When a module is run directly (python -m foo.bar or python script.py),
    __name__ is '__main__' which produces unhelpful log output. Replace it
    with the actual module name inferred from sys.argv so logs show the
    real service name.
    """
    if name == "__main__":
        import sys

        argv = sys.argv if sys.argv else []
        if len(argv) >= 3 and argv[1] == "-m":
            # python -m bridge_monitor.main  ->  bridge_monitor
            name = argv[2].rsplit(".", 1)[0] if "." in argv[2] else argv[2]
        elif argv:
            # python /path/to/bridge_monitor/main.py  ->  bridge_monitor
            stem = Path(argv[0]).stem
            name = Path(argv[0]).parent.name if stem == "main" else stem
        else:
            name = "app"
    return logging.getLogger(name)


def get_blockchain_logger(name: str) -> logging.Logger:
    """Get a logger that reuses the shared AITBC log formatting."""
    logger = logging.getLogger(name)
    logger.setLevel(_get_log_level())
    return logger


def configure_uvicorn_logging() -> None:
    """Make uvicorn loggers reuse the shared AITBC log format.

    Renames uvicorn's internal loggers to cleaner names so journal output
    reads as [uvicorn] instead of the confusing [uvicorn.error] / [uvicorn.access].
    """
    # Map uvicorn's internal logger names to cleaner display names
    _UVICORN_LOGGER_RENAMES = {
        "uvicorn": "uvicorn",
        "uvicorn.error": "uvicorn",
        "uvicorn.access": "uvicorn.access",
    }

    for logger_name, display_name in _UVICORN_LOGGER_RENAMES.items():
        logger = logging.getLogger(logger_name)
        logger.propagate = True
        logger.handlers = []
        # Override the name shown in log output without breaking uvicorn's
        # internal references (it looks up loggers by original name)
        logger.name = display_name

    # Suppress uvicorn access logs — request logging is handled by
    # RequestIDMiddleware and PerformanceLoggingMiddleware which use
    # appropriate log levels (DEBUG for routine, WARNING for errors).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def configure_logging(
    level: str = "INFO",
    structured: bool = False,
    service_name: str | None = None,
    to_file: bool = False,
) -> None:
    """Configure root logging level and format"""
    configure_uvicorn_logging()
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers for clean configuration
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler - use compact format for journal readability
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JournalFormatter())
    root_logger.addHandler(console_handler)

    # File handler with rotation (JSON format with timestamps for log aggregation)
    if to_file and service_name:
        log_file = _get_log_file_path(service_name)
        if log_file:
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
            )
            file_handler.setFormatter(StructuredFormatter(include_timestamp=True))
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
