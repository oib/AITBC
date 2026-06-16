#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-registry service
Uses centralized aitbc utilities for path configuration
"""

import os

from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# Agent Registry bind configuration
# Use AGENT_REGISTRY_BIND_HOST for bind address (default: 127.0.0.1)
# Use AGENT_REGISTRY_PORT for port (default: 8204)
bind_host = os.getenv("AGENT_REGISTRY_BIND_HOST", "127.0.0.1")
bind_port = os.getenv("AGENT_REGISTRY_PORT", "8204")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "app:app",
    "--host",
    bind_host,
    "--port",
    bind_port,
    "--app-dir",
    f"{REPO_DIR}/aitbc/agent_registry/src",
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
