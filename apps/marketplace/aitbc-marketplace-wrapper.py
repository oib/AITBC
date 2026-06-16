#!/usr/bin/env python3
"""
Wrapper script for marketplace service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = (
    "REPO_DIR:REPO_DIR/marketplace/scripts:REPO_DIR/marketplace/src:REPO_DIR/coordinator-api/src:REPO_DIR/packages/py/aitbc-sdk/src:REPO_DIR/packages/py/aitbc-crypto/src"
)
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)


log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "marketplace.py",
]
os.execvp(exec_cmd[0], exec_cmd)
