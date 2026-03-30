"""
Logging utilities for AITBC coordinator API
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
