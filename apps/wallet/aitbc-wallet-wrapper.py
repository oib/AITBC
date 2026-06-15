#!/usr/bin/env python3
"""
Wrapper script for aitbc-wallet service
Uses centralized aitbc utilities for path configuration
"""

import os
import sys
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = (
    f"{REPO_DIR}/apps/wallet/src:{REPO_DIR}/packages/py/aitbc-crypto/src:{REPO_DIR}/packages/py/aitbc-sdk/src:{REPO_DIR}"
)
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Override wallet directory if specified
wallet_dir = os.getenv("WALLET_DIR")
if wallet_dir:
    os.environ["WALLET_DIR"] = wallet_dir

# Execute the actual service
exec_cmd = ["/opt/aitbc/venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8108"]
os.execvp(exec_cmd[0], exec_cmd)
