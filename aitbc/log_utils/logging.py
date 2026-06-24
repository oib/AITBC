"""
AITBC Logging Module — compatibility shim.

All logging functionality lives in aitbc.aitbc_logging. This module re-exports
from it so that existing ``from aitbc.log_utils.logging import ...`` calls
continue to work. New code should import from aitbc.aitbc_logging directly.
"""

from ..aitbc_logging import (
    JournalFormatter,
    LogContext,
    StructuredFormatter,
    _get_log_file_path,
    _get_log_format,
    _get_log_level,
    configure_logging,
    configure_uvicorn_logging,
    get_blockchain_logger,
    get_logger,
    log_context,
    setup_logger,
)

BlockchainTextFormatter = JournalFormatter

__all__ = [
    "StructuredFormatter",
    "BlockchainTextFormatter",
    "JournalFormatter",
    "setup_logger",
    "get_logger",
    "get_blockchain_logger",
    "configure_logging",
    "configure_uvicorn_logging",
    "log_context",
    "LogContext",
    "_get_log_level",
    "_get_log_format",
    "_get_log_file_path",
]
