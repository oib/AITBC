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
AGENT_COORDINATOR_PORT = 8107
MARKETPLACE_PORT = 8081
COORDINATOR_API_PORT = 8203
WALLET_PORT = 8108
HERMES_PORT = 8103  # Deprecated: hermes service removed in v0.5.9 §8, use AGENT_COORDINATOR_PORT
EXCHANGE_PORT = 8001
REDIS_PORT = 6379

# CORS origins
DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:8080"]
PRODUCTION_CORS_ORIGINS = ["https://aitbc.io"]

# Bridge defaults (v0.7.0)
BRIDGE_FEE_BASIS_POINTS = 10  # 0.1% bridge fee
BRIDGE_TIMEOUT_SECONDS = 300  # 5 minutes for cross-chain transfer
BRIDGE_RETRY_LIMIT = 3  # retry attempts for failed bridge ops
BRIDGE_BATCH_SIZE = 10  # max transfers per batch operation
BRIDGE_MONITOR_INTERVAL = 60  # seconds between health checks
BRIDGE_STUCK_TRANSFER_TIMEOUT = 3600  # 1 hour — transfers pending longer are flagged

# Bridge multi-sig defaults (v0.7.1)
BRIDGE_MULTISIG_DEFAULT_THRESHOLD = 3  # M-of-N: minimum signatures required
BRIDGE_MULTISIG_DEFAULT_VALIDATORS = 5  # N: total validators in set
BRIDGE_MULTISIG_TIMEOUT = 3600  # seconds to collect signatures
BRIDGE_VALIDATOR_SET_GRACE_PERIOD = 7200  # seconds — old epoch valid during rotation
BRIDGE_BLOCK_SIGNATURE_REQUIRED = True  # require block header signatures

# Package version
PACKAGE_VERSION = __version__
