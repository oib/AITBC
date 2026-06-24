"""
AITBC Logging Module - Structured Logging Utilities

Compatibility re-exports from aitbc.aitbc_logging. New code should import
from aitbc.aitbc_logging directly.
"""

from .logging import (
    BlockchainTextFormatter,
    JournalFormatter,
    LogContext,
    StructuredFormatter,
    configure_logging,
    configure_uvicorn_logging,
    get_blockchain_logger,
    get_logger,
    log_context,
    setup_logger,
)

__all__ = [
    "BlockchainTextFormatter",
    "JournalFormatter",
    "LogContext",
    "StructuredFormatter",
    "configure_logging",
    "configure_uvicorn_logging",
    "get_blockchain_logger",
    "get_logger",
    "log_context",
    "setup_logger",
]
