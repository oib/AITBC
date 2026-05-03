"""
AITBC Core Utilities
"""

from . import logging  # noqa: F811 — aitbc.logging submodule, not stdlib
from .logging import configure_logging, get_logger
from .middleware import (
    RequestIDMiddleware,
    PerformanceLoggingMiddleware,
    RequestValidationMiddleware,
    ErrorHandlerMiddleware,
)

# Re-export constants for compatibility
from .constants import (
    DATA_DIR,
    LOG_DIR,
    CONFIG_DIR,
    REPO_DIR,
    KEYSTORE_DIR,
    BLOCKCHAIN_DATA_DIR,
    MARKETPLACE_DATA_DIR,
    ENV_FILE,
    NODE_ENV_FILE,
    BLOCKCHAIN_RPC_PORT,
    BLOCKCHAIN_P2P_PORT,
    AGENT_COORDINATOR_PORT,
    MARKETPLACE_PORT,
    PACKAGE_VERSION,
)

__all__ = [
    "logging",
    "configure_logging",
    "get_logger",
    "RequestIDMiddleware",
    "PerformanceLoggingMiddleware",
    "RequestValidationMiddleware",
    "ErrorHandlerMiddleware",
    "DATA_DIR",
    "LOG_DIR",
    "CONFIG_DIR",
    "REPO_DIR",
    "KEYSTORE_DIR",
    "BLOCKCHAIN_DATA_DIR",
    "MARKETPLACE_DATA_DIR",
    "ENV_FILE",
    "NODE_ENV_FILE",
    "BLOCKCHAIN_RPC_PORT",
    "BLOCKCHAIN_P2P_PORT",
    "AGENT_COORDINATOR_PORT",
    "MARKETPLACE_PORT",
    "PACKAGE_VERSION",
]
