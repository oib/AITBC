#!/usr/bin/env python3
"""
Wrapper script for hermes service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = "REPO_DIR:REPO_DIR/hermes/src"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)


# Load node.env to get additional config
if os.path.exists(NODE_ENV_FILE):
    with open(NODE_ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

if "HERMES_DB_PATH" not in os.environ:
    os.environ["HERMES_DB_PATH"] = str(DATA_DIR / "data/hermes_coin_requests.db")

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# hermes bind configuration
# Use HERMES_BIND_HOST for bind address (default: 0.0.0.0)
# Use HERMES_BIND_PORT for port (default: 8103)
bind_host = os.getenv("HERMES_BIND_HOST", "0.0.0.0")
bind_port = os.getenv("HERMES_BIND_PORT", "8103")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "hermes_service.main:app",
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
