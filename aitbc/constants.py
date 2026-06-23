"""
AITBC Common Constants
Centralized constants for AITBC system paths and configuration
"""

from pathlib import Path

from ._version import __version__

# AITBC System Paths
DATA_DIR = Path("/var/lib/aitbc")
CONFIG_DIR = Path("/etc/aitbc")
LOG_DIR = Path("/var/log/aitbc")
REPO_DIR = Path("/opt/aitbc")

# Common subdirectories
KEYSTORE_DIR = DATA_DIR / "keystore"
BLOCKCHAIN_DATA_DIR = DATA_DIR / "data" / "ait-mainnet"
MARKETPLACE_DATA_DIR = DATA_DIR / "data" / "marketplace"

# Configuration files
ENV_FILE = CONFIG_DIR / ".env"
NODE_ENV_FILE = CONFIG_DIR / "node.env"

# Default ports
BLOCKCHAIN_RPC_PORT = 8202
BLOCKCHAIN_P2P_PORT = 8200
AGENT_COORDINATOR_PORT = 9001
MARKETPLACE_PORT = 8081
COORDINATOR_API_PORT = 8203
WALLET_PORT = 8108
HERMES_PORT = 8103  # Deprecated: hermes service removed in v0.5.9 §8, use AGENT_COORDINATOR_PORT
EXCHANGE_PORT = 8001
REDIS_PORT = 6379

# CORS origins
DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:8080"]
PRODUCTION_CORS_ORIGINS = ["https://aitbc.io"]

# Package version
PACKAGE_VERSION = __version__
