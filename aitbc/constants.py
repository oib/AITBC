"""
AITBC Common Constants
Centralized constants for AITBC system paths and configuration
"""

from pathlib import Path

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
BLOCKCHAIN_RPC_PORT = 8006
BLOCKCHAIN_P2P_PORT = 7070
AGENT_COORDINATOR_PORT = 9001
MARKETPLACE_PORT = 8081

# Package version
PACKAGE_VERSION = "0.3.0"
