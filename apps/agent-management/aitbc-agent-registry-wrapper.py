#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-registry service
Uses centralized aitbc utilities for path configuration
"""

import sys
import os
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))

from aitbc import ENV_FILE, NODE_ENV_FILE, REPO_DIR, DATA_DIR, LOG_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    f"{REPO_DIR}/apps/agent-services/agent-registry/src/app.py"
]
os.execvp(exec_cmd[0], exec_cmd)
