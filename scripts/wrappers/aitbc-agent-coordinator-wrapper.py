#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-coordinator service
Uses centralized aitbc utilities for path configuration
"""

import sys
import os
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))

from aitbc import ENV_FILE, NODE_ENV_FILE, REPO_DIR, DATA_DIR, LOG_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}:{REPO_DIR}/apps/agent-coordinator/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Create required directories
from aitbc.paths import ensure_dir
ensure_dir(DATA_DIR / "agent-coordinator")
ensure_dir(LOG_DIR / "agent-coordinator")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "src.app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "9001"
]
os.execvp(exec_cmd[0], exec_cmd)
