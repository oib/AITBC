"""
AITBC Structured Logging Module

Provides JSON-formatted structured logging for all AITBC services.
"""

import json
import logging
import sys
import structlog
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

        # Include extra fields
        skip_fields = {
            "name", "msg", "args", "created", "relativeCreated",
            "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "pathname", "filename", "module", "levelno", "levelname",
            "msecs", "thread", "threadName", "process", "processName",
            "taskName", "message",
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

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    formatter = StructuredLogFormatter(service_name=service_name, env=env)

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_audit_logger(service_name: str, env: str = "production") -> logging.Logger:
    """Get or create an audit logger for a service."""
    audit_name = f"{service_name}.audit"
    return setup_logger(name=audit_name, service_name=service_name, env=env)


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for structured logging"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    
    # Configure standard logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance"""
    return structlog.get_logger(name)
