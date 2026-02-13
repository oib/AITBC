from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Any, Optional

import json


class StructuredLogFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging - consistent with coordinator API."""
    
    RESERVED = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "process",
        "processName",
    }

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service": "aitbc-blockchain-node",
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in self.RESERVED or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        return json.dumps(payload, default=str)


class AuditLogger:
    """Audit logger for tracking sensitive operations - consistent with coordinator API."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def log(self, action: str, user_id: Optional[str] = None, resource_id: Optional[str] = None, 
            details: Optional[dict] = None, success: bool = True) -> None:
        """Log an audit event."""
        self.logger.info(
            "audit_event",
            extra={
                "audit": {
                    "action": action,
                    "user_id": user_id,
                    "resource_id": resource_id,
                    "details": details or {},
                    "success": success
                }
            }
        )


def configure_logging(level: Optional[str] = None, json_format: bool = True) -> None:
    """Configure structured logging for the blockchain node."""
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    
    if json_format:
        handler = logging.StreamHandler(sys.stdout)
        formatter = StructuredLogFormatter()
        handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
    
    root.addHandler(handler)
    root.setLevel(log_level)
    
    logging.getLogger('uvicorn').setLevel(log_level)
    logging.getLogger('uvicorn.access').setLevel(log_level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    if not logging.getLogger().handlers:
        configure_logging()
    return logging.getLogger(name)


def get_audit_logger(name: str = "audit") -> AuditLogger:
    """Get an audit logger instance."""
    return AuditLogger(get_logger(name))
