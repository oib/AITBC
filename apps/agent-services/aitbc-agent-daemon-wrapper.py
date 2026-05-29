#!/usr/bin/env python3
"""
Wrapper script for aitbc-agent-daemon service
Supports multichain by spawning daemon instances for each configured chain
"""

import sys
import os
import subprocess
from pathlib import Path

# Add aitbc to path
sys.path.insert(0, str(Path("/opt/aitbc")))
sys.path.insert(0, str(Path("/opt/aitbc/aitbc")))

from aitbc import ENV_FILE, NODE_ENV_FILE, REPO_DIR, DATA_DIR, LOG_DIR, KEYSTORE_DIR

# Set up environment using aitbc constants
os.environ["AITBC_ENV_FILE"] = str(ENV_FILE)
os.environ["AITBC_NODE_ENV_FILE"] = str(NODE_ENV_FILE)
os.environ["PYTHONPATH"] = f"{REPO_DIR}:{REPO_DIR}/packages/py/aitbc-agent-sdk/src:{REPO_DIR}/apps/agent-coordinator/scripts:{REPO_DIR}"
os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["LOG_DIR"] = str(LOG_DIR)

# Get chain configuration from environment
# Support both single chain (CHAIN_ID) and multiple chains (AGENT_DAEMON_CHAINS)
chains_str = os.getenv("AGENT_DAEMON_CHAINS", "")
if chains_str:
    chains = [c.strip() for c in chains_str.split(",")]
else:
    chains = [os.getenv("CHAIN_ID", "ait-mainnet")]

# Spawn daemon processes for each chain
daemon_script = f"{REPO_DIR}/apps/agent-coordinator/scripts/agent_daemon.py"
base_args = [
    "--wallet", "temp-agent",
    "--address", "ait1d18e286fc0c12888aca94732b5507c8787af71a5",
    "--password-file", str(KEYSTORE_DIR / ".agent_daemon_password"),
    "--keystore-dir", str(KEYSTORE_DIR),
    "--rpc-url", "http://localhost:8006",
    "--poll-interval", "2",
    "--reply-message", "pong",
    "--trigger-message", "ping"
]

if len(chains) == 1:
    # Single chain: exec directly (replaces wrapper process)
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
    # Multiple chains: spawn subprocesses and wait
    processes = []
    for chain_id in chains:
        db_path = f"/var/lib/aitbc/data/{chain_id}/chain.db"
        cmd = [
            "/opt/aitbc/venv/bin/python",
            daemon_script,
            *base_args,
            "--db-path", db_path,
            "--chain-id", chain_id
        ]
        print(f"Starting agent daemon for chain: {chain_id}")
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
