#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-daemon service
Supports multichain by spawning daemon instances for each configured chain
Also supports Hermes API polling for agent messaging
"""

import os
import subprocess
import sys
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))

from aitbc import DATA_DIR, ENV_FILE, KEYSTORE_DIR, LOG_DIR, NODE_ENV_FILE, REPO_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}:{REPO_DIR}/packages/py/aitbc-agent-sdk/src:{REPO_DIR}/apps/agent-coordinator/scripts:{REPO_DIR}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Check if Hermes polling is enabled
enable_hermes = os.getenv("ENABLE_HERMES_POLLING", "false").lower() == "true"
hermes_agent_ids = os.getenv("HERMES_AGENT_IDS", "")
hermes_coordinator_url = os.getenv("HERMES_COORDINATOR_URL", "http://localhost:8011")

processes = []

# Spawn Hermes polling daemons if enabled
if enable_hermes and hermes_agent_ids:
    hermes_daemon_script = f"{REPO_DIR}/apps/agent-coordinator/scripts/hermes_polling_daemon.py"
    hermes_service_url = os.getenv("HERMES_SERVICE_URL", "http://localhost:8014")
    agent_ids = [aid.strip() for aid in hermes_agent_ids.split(",")]

    for agent_id in agent_ids:
        cmd = [
            "/opt/aitbc/venv/bin/python",
            hermes_daemon_script,
            "--coordinator-url", hermes_coordinator_url,
            "--agent-id", agent_id,
            "--poll-interval", "10",
            "--log-level", "INFO",
            "--hermes-service-url", hermes_service_url
        ]
        print(f"Starting Hermes polling daemon for agent: {agent_id}")
        proc = subprocess.Popen(cmd)
        processes.append(proc)

# Get chain configuration from environment
# Support both single chain (CHAIN_ID) and multiple chains (AGENT_DAEMON_CHAINS)
chains_str = os.getenv("AGENT_DAEMON_CHAINS", "")
if chains_str:
    chains = [c.strip() for c in chains_str.split(",")]
else:
    # Default to empty if not set - only run Hermes polling if no chains configured
    chains = []

# Spawn daemon processes for each chain
daemon_script = f"{REPO_DIR}/apps/agent-coordinator/scripts/agent_daemon.py"
base_args = [
    "--wallet", "my-agent-wallet",
    "--address", "aitbc1c10f0e4fb1d162bb27af88a698b8c2e6e39a844f",
    "--password-file", str(KEYSTORE_DIR / ".agent_daemon_password"),
    "--keystore-dir", str(KEYSTORE_DIR),
    "--rpc-url", "http://localhost:8006",
    "--poll-interval", "10",
    "--reply-message", "pong",
    "--trigger-message", "ping"
]

# If we have Hermes daemons running or multiple chains, use subprocess mode
if processes or len(chains) > 1:
    # Spawn blockchain daemons as subprocesses
    for chain_id in chains:
        db_path = f"/var/lib/aitbc/data/{chain_id}/chain.db"
        cmd = [
            "/opt/aitbc/venv/bin/python",
            daemon_script,
            *base_args,
            "--db-path", db_path,
            "--chain-id", chain_id
        ]
        print(f"Starting blockchain agent daemon for chain: {chain_id}")
        proc = subprocess.Popen(cmd)
        processes.append(proc)

    # Wait for all processes
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("Shutting down agent daemons...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.wait()
elif len(chains) == 1:
    # Single chain with no Hermes: exec directly (replaces wrapper process)
    chain_id = chains[0]
    db_path = f"/var/lib/aitbc/data/{chain_id}/chain.db"
    exec_cmd = [
        "/opt/aitbc/venv/bin/python",
        daemon_script,
        *base_args,
        "--db-path", db_path,
        "--chain-id", chain_id
    ]
    os.execvp(exec_cmd[0], exec_cmd)
else:
    # No chains configured, only Hermes daemons running
    print("No blockchain chains configured, only Hermes polling active")
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("Shutting down Hermes daemons...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.wait()
