#!/usr/bin/env python3
"""
Wrapper script for wallet service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = (
    "REPO_DIR:REPO_DIR/wallet/src:REPO_DIR/packages/py/aitbc-crypto/src:REPO_DIR/packages/py/aitbc-sdk/src"
)
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

wallet_dir = os.getenv("WALLET_DIR")
if wallet_dir:
    os.environ["WALLET_DIR"] = wallet_dir


log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# wallet bind configuration
# Use WALLET_BIND_HOST for bind address (default: 0.0.0.0)
# Use WALLET_BIND_PORT for port (default: 8108)
bind_host = os.getenv("WALLET_BIND_HOST", "0.0.0.0")
bind_port = os.getenv("WALLET_BIND_PORT", "8108")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    bind_host,
    "--port",
    bind_port,
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
