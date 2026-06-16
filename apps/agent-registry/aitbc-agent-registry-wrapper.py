#!/usr/bin/env python3
"""agent-registry service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")

sys.path.insert(0, str(REPO_DIR))

# Import AITBC utilities
from aitbc import (  # noqa: E402
    LOG_DIR,
    configure_logging,
    get_logger,
)

# Configure logging
configure_logging(
    level="INFO",
    service_name="agent-registry",
    to_file=True,
)

logger = get_logger(__name__)
logger.info("Starting agent-registry service")

# agent-registry bind configuration
bind_host = os.getenv("AGENT_REGISTRY_HOST", "127.0.0.1")
bind_port = os.getenv("AGENT_REGISTRY_PORT", "8003")

log_level = os.getenv("LOG_LEVEL", "info").lower()
access_log = os.getenv("ACCESS_LOG", "true").lower() in ("1", "true", "yes")

# Execute the actual service
exec_cmd = [
    sys.executable,
    "-m",
    "uvicorn",
    "aitbc.agent_registry.src.app:app",
    "--host",
    bind_host,
    "--port",
    bind_port,
    "--log-level",
    log_level,
]

if access_log:
    exec_cmd.append("--access-log")

logger.info(f"Executing: {' '.join(exec_cmd)}")

# Ensure PYTHONPATH is set for the child process
env = os.environ.copy()
env["PYTHONPATH"] = "/opt/aitbc"

os.execvpe(exec_cmd[0], exec_cmd, env)
