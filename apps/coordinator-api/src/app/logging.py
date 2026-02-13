"""
Logging configuration for the AITBC Coordinator API

Provides structured JSON logging for better observability and log parsing.
"""

import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict, Optional
from pythonjsonlogger import jsonlogger


class StructuredLogFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        log_record['service'] = 'aitbc-coordinator-api'
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno
        
        if record.exc_info:
            log_record['exception'] = self.format_exception(record.exc_info)
    
    @staticmethod
    def format_exception(exc_info) -> Optional[Dict[str, Any]]:
        """Format exception info for JSON output."""
        if exc_info is None:
            return None
        import traceback
        return {
            'type': exc_info[0].__name__ if exc_info[0] else None,
            'message': str(exc_info[1]) if exc_info[1] else None,
            'traceback': traceback.format_exception(*exc_info) if exc_info[0] else None
        }


class AuditLogger:
    """Audit logger for tracking sensitive operations."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def log(self, action: str, user_id: Optional[str] = None, resource_id: Optional[str] = None, 
            details: Optional[Dict[str, Any]] = None, success: bool = True) -> None:
        """Log an audit event."""
        self.logger.info(
            "audit_event",
            extra={
                'audit': {
                    'action': action,
                    'user_id': user_id,
                    'resource_id': resource_id,
                    'details': details or {},
                    'success': success
                }
            }
        )


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Setup structured logging for the application."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    if json_format:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredLogFormatter(
            '%(timestamp)s %(level)s %(message)s'
        ))
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
    
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper()))
    
    logging.getLogger('uvicorn').setLevel(level)
    logging.getLogger('uvicorn.access').setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def get_audit_logger(name: str = "audit") -> AuditLogger:
    """Get an audit logger instance."""
    return AuditLogger(get_logger(name))


# Initialize default logging on import
setup_logging()
