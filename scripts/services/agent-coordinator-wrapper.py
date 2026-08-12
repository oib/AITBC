#!/usr/bin/env python3
"""agent-coordinator service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path(__file__).resolve().parents[3]
SERVICE_DIR = REPO_DIR / "apps" / "agent-coordinator" / "src"

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR))

# Import AITBC utilities
from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402

# Configure logging
configure_logging(
    level="INFO",
    service_name="agent-coordinator",
    to_file=True,
)

logger = get_logger(__name__)
logger.info("Starting agent-coordinator service")

# Execute service
exec_cmd = [
    sys.executable,
    "-m",
    "agent_app.main",
]

logger.info(f"Executing: {' '.join(exec_cmd)}")

# Ensure PYTHONPATH is set for the child process
env = os.environ.copy()
env["PYTHONPATH"] = f"{REPO_DIR}:{SERVICE_DIR}"

os.execvpe(exec_cmd[0], exec_cmd, env)
