#!/usr/bin/env python3
"""blockchain-p2p service wrapper"""

import os
import sys
from pathlib import Path

# Add AITBC to path
REPO_DIR = Path("/opt/aitbc")
SERVICE_DIR = Path("/opt/aitbc/apps/blockchain-node")

sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SERVICE_DIR / "src"))


def build_cmd() -> list[str]:
    """Build the gossip-relay argv from the environment.

    The port comes from ``P2P_BIND_PORT`` (default 7070 — the value the
    wrapper hardcoded before this env was honoured, which is what the live
    hub still runs). The host comes from ``P2P_BIND_HOST`` (default
    127.0.0.1 — the relay is a hub-internal service per
    docs/architecture/4_blockchain-node.md and followers never connect to
    it, so binding all interfaces only exposed an unauthenticated publish
    endpoint, #1065). A deployment that needs off-host gossip sets
    P2P_BIND_HOST explicitly.
    """
    return [
        sys.executable,
        "-m",
        "aitbc_chain.gossip.relay",
        "--host",
        os.environ.get("P2P_BIND_HOST", "127.0.0.1"),
        "--port",
        os.environ.get("P2P_BIND_PORT", "7070"),
        "--access-log",
    ]


def main() -> None:
    # Import AITBC utilities
    from aitbc.aitbc_logging import configure_logging, get_logger  # noqa: E402

    # Configure logging
    configure_logging(
        level="INFO",
        service_name="blockchain-p2p",
        to_file=True,
    )

    logger = get_logger(__name__)
    logger.info("Starting blockchain-p2p service")

    exec_cmd = build_cmd()
    logger.info(f"Executing: {' '.join(exec_cmd)}")

    # Ensure PYTHONPATH is set for the child process
    env = os.environ.copy()
    env["PYTHONPATH"] = "/opt/aitbc:/opt/aitbc/apps/blockchain-node/src"

    os.execvpe(exec_cmd[0], exec_cmd, env)


if __name__ == "__main__":
    main()
