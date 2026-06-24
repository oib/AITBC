"""
AITBC Common Constants
Centralized constants for AITBC system paths and configuration
"""

import os
from pathlib import Path

from ._version import __version__

# AITBC root directory. When set via AITBC_HOME env var, all derived paths
# (data, config, logs, repo) follow it for portability. When unset, the
# traditional system paths are used as defaults (backward compatible).
AITBC_HOME = Path(os.getenv("AITBC_HOME", "/opt/aitbc"))

# Derive sub-path defaults: if AITBC_HOME is explicitly set, use subdirs
# under it; otherwise use the traditional system paths.
_HOME_OVERRIDE = bool(os.getenv("AITBC_HOME"))
_DATA_DEFAULT = str(AITBC_HOME / "data") if _HOME_OVERRIDE else "/var/lib/aitbc"
_CONFIG_DEFAULT = str(AITBC_HOME / "config") if _HOME_OVERRIDE else "/etc/aitbc"
_LOG_DEFAULT = str(AITBC_HOME / "logs") if _HOME_OVERRIDE else "/var/log/aitbc"
_REPO_DEFAULT = str(AITBC_HOME)

# AITBC System Paths — each individually overridable via env var
DATA_DIR = Path(os.getenv("AITBC_DATA_DIR", _DATA_DEFAULT))
CONFIG_DIR = Path(os.getenv("AITBC_CONFIG_DIR", _CONFIG_DEFAULT))
LOG_DIR = Path(os.getenv("AITBC_LOG_DIR", _LOG_DEFAULT))
REPO_DIR = Path(os.getenv("AITBC_REPO_DIR", _REPO_DEFAULT))

# Common subdirectories
KEYSTORE_DIR = DATA_DIR / "keystore"
BLOCKCHAIN_DATA_DIR = DATA_DIR / "data" / "ait-mainnet"
MARKETPLACE_DATA_DIR = DATA_DIR / "data" / "marketplace"

# Configuration files
ENV_FILE = CONFIG_DIR / ".env"
NODE_ENV_FILE = CONFIG_DIR / "node.env"

# Startup validation: when AITBC_HOME is explicitly set, verify it exists
# and is writable. This catches misconfigurations early (e.g. typos in the
# env var). When using the default (/opt/aitbc), skip validation to avoid
# breaking fresh dev checkouts where the directory doesn't exist yet.
if _HOME_OVERRIDE:
    if not AITBC_HOME.is_dir():
        raise RuntimeError(f"AITBC_HOME={AITBC_HOME} does not exist or is not a directory")
    if not os.access(AITBC_HOME, os.W_OK):
        raise RuntimeError(f"AITBC_HOME={AITBC_HOME} is not writable")

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
