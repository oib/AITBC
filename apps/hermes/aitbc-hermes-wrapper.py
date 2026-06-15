#!/usr/bin/env python3
"""
Wrapper script for aitbc-hermes service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Load node.env to get HERMES_DB_PATH
if os.path.exists(NODE_ENV_FILE):
    with open(NODE_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}/apps/hermes/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Ensure HERMES_DB_PATH is set for the service
if "HERMES_DB_PATH" not in os.environ:
    os.environ["HERMES_DB_PATH"] = str(DATA_DIR / "data" / "hermes_coin_requests.db")

# Get Hermes configuration from environment or use defaults
hermes_host = os.getenv("HERMES_BIND_HOST", "127.0.0.1")
hermes_port = os.getenv("HERMES_PORT", "8103")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "hermes_service.main:app",
    "--host",
    hermes_host,
    "--port",
    hermes_port,
    "--log-level",
    "critical",
    "--no-access-log",
]
os.execvp(exec_cmd[0], exec_cmd)
