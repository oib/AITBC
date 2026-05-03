"""
Logging module (alias for aitbc_logging)
This module provides a compatibility layer for imports from aitbc.logging
"""

import logging
import sys
from typing import Optional

def setup_logger(
    name: str,
    level: str = "INFO",
    format_string: Optional[str] = None
) -> logging.Logger:
    """Setup a logger with consistent formatting"""
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(format_string)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)

def configure_logging(level: str = "INFO", format_string: str = None):
    """Configure logging with default settings"""
    return setup_logger("aitbc", level=level, format_string=format_string)

__all__ = ["get_logger", "setup_logger", "configure_logging"]
