"""AITBC structured logging module.

Mirrors the structured logger in ``packages/py/aitbc-core/src/aitbc/logging.py``
so the repo-root ``aitbc`` package can be used from the CLI and tests.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional


class StructuredLogFormatter(logging.Formatter):
    """JSON structured log formatter for AITBC services."""

    def __init__(self, service_name: str, env: str = "production"):
        super().__init__()
        self.service_name = service_name
        self.env = env

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "env": self.env,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)

        skip_fields = {
            "name",
            "msg",
            "args",
            "created",
            "relativeCreated",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "pathname",
            "filename",
            "module",
            "levelno",
            "levelname",
            "msecs",
            "thread",
            "threadName",
            "process",
            "processName",
            "taskName",
            "message",
        }
        for key, value in record.__dict__.items():
            if key not in skip_fields and not key.startswith("_"):
                try:
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        return json.dumps(log_data)


def setup_logger(
    name: str,
    service_name: str,
    env: str = "production",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Set up a structured logger for an AITBC service."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = StructuredLogFormatter(service_name=service_name, env=env)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance (no setup side effects)."""
    return logging.getLogger(name)


def get_audit_logger(service_name: str, env: str = "production") -> logging.Logger:
    """Get or create an audit logger for a service."""
    audit_name = f"{service_name}.audit"
    return setup_logger(name=audit_name, service_name=service_name, env=env)
