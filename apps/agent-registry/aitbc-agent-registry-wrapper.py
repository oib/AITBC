#!/usr/bin/env python3
"""
Wrapper script for {service_name} service
Uses centralized aitbc utilities for path configuration
"""

import os
from pathlib import Path
from aitbc import DATA_DIR, ENV_FILE, LOG_DIR, NODE_ENV_FILE, REPO_DIR, KEYSTORE_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = "{PYTHONPATH}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

{wallet_env_code}

{load_node_env_code}

{db_path_code}

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# {service_name} bind configuration
# Use {bind_host_env} for bind address (default: {bind_host_default})
# Use {port_env} for port (default: {port_default})
bind_host = os.getenv("{bind_host_env}", "{bind_host_default}")
bind_port = os.getenv("{port_env}", "{port_default}")

# Execute the actual service
exec_cmd = [
    "/opt/aitbc/venv/bin/python",
    "-m",
    "uvicorn",
    "{module}",
    "--host",
    bind_host,
    "--port",
    bind_port,
{workers_code}{extra_uvicorn_code}
    "--log-level",
    log_level,
]
if access_log:
    exec_cmd.append("--access-log")
os.execvp(exec_cmd[0], exec_cmd)
