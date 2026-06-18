#!/usr/bin/env python3
"""Bridge monitor service wrapper."""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/bridge-monitor")

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR / "src"))

# Import AITBC utilities
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402

# Configure logging
configure_logging(
    level="INFO",
    service_name="bridge-monitor",
    to_file=True,
)

logger = get_logger(__name__)
logger.info("Starting bridge-monitor service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "bridge_monitor.main",
]

logger.info(f"Executing: {' '.join(exec_cmd)}")

# Ensure PYTHONPATH is set for the child process
env = os.environ.copy()
env["PYTHONPATH"] = "/opt/aitbc:/opt/aitbc/apps/bridge-monitor/src"

os.execvpe(exec_cmd[0], exec_cmd, env)
