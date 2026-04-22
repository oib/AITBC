"""
AITBC Package
Centralized utilities for AITBC applications
"""

from .aitbc_logging import get_logger, setup_logger
from .constants import (
    DATA_DIR,
    CONFIG_DIR,
    LOG_DIR,
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
from .exceptions import (
    AITBCError,
    ConfigurationError,
    NetworkError,
    AuthenticationError,
    EncryptionError,
    DatabaseError,
    ValidationError,
    BridgeError,
)
from .env import (
    get_env_var,
    get_required_env_var,
    get_bool_env_var,
    get_int_env_var,
    get_float_env_var,
    get_list_env_var,
)

__version__ = "0.3.0"
__all__ = [
    # Logging
    "get_logger",
    "setup_logger",
    # Constants
    "DATA_DIR",
    "CONFIG_DIR",
    "LOG_DIR",
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
    # Exceptions
    "AITBCError",
    "ConfigurationError",
    "NetworkError",
    "AuthenticationError",
    "EncryptionError",
    "DatabaseError",
    "ValidationError",
    "BridgeError",
    # Environment helpers
    "get_env_var",
    "get_required_env_var",
    "get_bool_env_var",
    "get_int_env_var",
    "get_float_env_var",
    "get_list_env_var",
]
