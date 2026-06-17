#!/usr/bin/env python3
"""marketplace service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/marketplace")

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR))

# Import AITBC utilities
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402

# Configure logging
configure_logging(
    level="INFO",
    service_name="marketplace",
    to_file=True,
)

logger = get_logger(__name__)
logger.info("Starting marketplace service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "marketplace_service.main",
]

logger.info(f"Executing: {' '.join(exec_cmd)}")

# Ensure PYTHONPATH is set for the child process
env = os.environ.copy()
env["PYTHONPATH"] = "/opt/aitbc:/opt/aitbc/apps/marketplace/src"

os.execvpe(exec_cmd[0], exec_cmd, env)
