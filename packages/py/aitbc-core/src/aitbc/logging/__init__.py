from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Any, Optional
import json

class StructuredLogFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process"
    }

    def __init__(self, service_name: str, env: str = "production"):
        super().__init__()
        self.service_name = service_name
        self.env = env

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "service": self.service_name,
            "env": self.env,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        
        # Add stack info if present
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # Add extra fields passed in the record
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                # Make sure value is JSON serializable
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)

        return json.dumps(payload)


def setup_logger(
    name: str,
    service_name: str,
    env: str = "production",
    level: int | str = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Setup a logger with structured JSON formatting."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Don't propagate to root logger
    logger.propagate = False
    
    # Remove existing handlers to avoid duplicates
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        
    formatter = StructuredLogFormatter(service_name=service_name, env=env)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get an existing logger or create a generic one if it doesn't exist."""
    return logging.getLogger(name)


def get_audit_logger(service_name: str) -> logging.Logger:
    """Get a dedicated logger for security/audit events."""
    logger = logging.getLogger(f"{service_name}.audit")
    if not logger.handlers:
        logger = setup_logger(
            name=f"{service_name}.audit",
            service_name=service_name,
            level=logging.INFO
        )
    return logger
