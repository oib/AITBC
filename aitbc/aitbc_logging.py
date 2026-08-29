"""
AITBC Logging Module
Centralized logging utilities for the AITBC project

Output format is fixed and deliberately not configurable: the console (systemd journal)
always gets `JournalFormatter`, and a rotating file, when one is configured, always gets
`StructuredFormatter`. Human-readable where a human reads it, JSON where a parser does.

That was decided in 1b81d840 ("switch systemd journal logging to compact human-readable
format"), which removed the conditional that chose between them. What it did not remove was
the way to ask for the other branch, so until V23-78 this module still offered three: a
`structured` flag on `setup_logger` and `configure_logging`, a `format_string` on the former,
and a `LOG_FORMAT` environment variable read by `_get_log_format`. None of the three had been
connected to anything since 19 June 2026. `LOG_FORMAT=json` was nevertheless set in five
systemd units and asserted by two release gates, which is the reason to delete a dead switch
rather than leave it lying around: people go on wiring things up to it.
"""

import json
import logging
import logging.handlers
import os
import re
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


# Backward-compat alias: v0.5.11 renamed BlockchainTextFormatter → JournalFormatter.
# The alias is also exported from aitbc.log_utils; keep it here so direct
# importers of the canonical module don't break.
BlockchainTextFormatter = JournalFormatter


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


def _get_log_file_path(service_name: str) -> Path | None:
    """Get log file path from environment."""
    log_dir = os.getenv("LOG_DIR")
    if not log_dir:
        return None
    log_path = Path(log_dir)
    # Refuse relative/placeholder env values to avoid writing a log tree into
    # whatever directory happens to be the current working directory.
    if not log_path.is_absolute():
        return None
    service_path = log_path / service_name
    service_path.mkdir(parents=True, exist_ok=True)
    return service_path / f"{service_name}.log"


def setup_logger(
    name: str,
    level: str = "INFO",
    service_name: str | None = None,
    to_file: bool = False,
    rotation: str = "daily",
    max_files: int = 7,
) -> logging.Logger:
    """Setup a logger with consistent formatting and optional file rotation.

    Which formatter is used is not configurable, by decision: console output is always
    `JournalFormatter` and file output is always `StructuredFormatter`. See the module
    docstring for why this function used to take `structured` and `format_string`.
    """
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


_HTTPX_STATUS_RE = re.compile(r'"HTTP/\d+(?:\.\d+)? (\d{3})[^"]*"')


class _HttpxStatusFilter(logging.Filter):
    """Upgrade httpx request logs to WARNING/ERROR when the response is an error."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        match = _HTTPX_STATUS_RE.search(msg)
        if match:
            try:
                status = int(match.group(1))
            except ValueError:
                return True
            if status >= 500:
                record.levelno = logging.ERROR
                record.levelname = "ERROR"
            elif status >= 400:
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
        return True


def configure_httpx_logging() -> None:
    """Add a filter so httpx logs 4xx at WARNING and 5xx at ERROR."""
    httpx_logger = logging.getLogger("httpx")
    if not any(isinstance(f, _HttpxStatusFilter) for f in httpx_logger.filters):
        httpx_logger.addFilter(_HttpxStatusFilter())


def configure_logging(
    level: str = "INFO",
    service_name: str | None = None,
    to_file: bool = False,
) -> None:
    """Configure root logging level and handlers.

    Console is always `JournalFormatter`, file is always `StructuredFormatter`; see the
    module docstring. This took a `structured` flag that has never been read.
    """
    configure_uvicorn_logging()
    configure_httpx_logging()
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
