"""
AITBC Logging Module
Centralized logging utilities for the AITBC project
"""

import logging
import sys
import json
from typing import Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager

class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for log aggregation"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

def setup_logger(
    name: str,
    level: str = "INFO",
    format_string: Optional[str] = None,
    structured: bool = False
) -> logging.Logger:
    """Setup a logger with consistent formatting"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        if structured:
            formatter = StructuredFormatter()
        else:
            if format_string is None:
                format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            formatter = logging.Formatter(format_string)
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)

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

@contextmanager
def log_context(**kwargs):
    """Context manager for adding contextual information to logs"""
    logger = logging.getLogger()
    extra = {'extra': kwargs}
    
    class ContextFilter(logging.Filter):
        def filter(self, record):
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
    
    def __init__(self, **kwargs):
        self.context = kwargs
    
    def __enter__(self):
        return log_context(**self.context).__enter__()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
