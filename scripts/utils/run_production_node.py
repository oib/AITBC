#!/usr/bin/env python3
"""
Production launcher for AITBC blockchain node.
Sets up environment, initializes genesis if needed, and starts the node.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from eth_account import Account

# Configuration
CHAIN_ID = "ait-mainnet"
DATA_DIR = Path("/var/lib/aitbc/data/ait-mainnet")
DB_PATH = DATA_DIR / "chain.db"

# The proposer identity is config-driven: PROPOSER_KEY / PROPOSER_ID come from
# the node environment (/etc/aitbc/node.env on the fleet). This launcher used to
# derive the id from sha256("aitbc1genesis") -- a retired host-name key whose
# address (0xEe10...) is not the address the fleet proposes under -- and to
# require a keystore file of the same retired name. Both made the script refuse
# or misidentify every node it ran on.
proposer_key = os.getenv("PROPOSER_KEY")
if not proposer_key:
    print("[!] PROPOSER_KEY environment variable not set.")
    print("    Set PROPOSER_KEY to the hex private key of this node's proposer (see /etc/aitbc/node.env).")
    sys.exit(1)

# PROPOSER_ID is whatever the configured key controls. A PROPOSER_ID that
# disagrees with it is a config error: the node would sign blocks under the key
# while naming another identity, so refuse rather than pick one silently.
try:
    derived_proposer_id = Account.from_key(proposer_key.strip()).address
except Exception:
    print("[!] PROPOSER_KEY is not a valid secp256k1 private key.")
    sys.exit(1)

proposer_id = os.getenv("PROPOSER_ID", derived_proposer_id)
if proposer_id.strip().lower() != derived_proposer_id.lower():
    print(f"[!] PROPOSER_ID={proposer_id} does not match the configured PROPOSER_KEY (which controls {derived_proposer_id}).")
    sys.exit(1)

# Set environment variables
os.environ["CHAIN_ID"] = CHAIN_ID
os.environ["SUPPORTED_CHAINS"] = CHAIN_ID
os.environ["DB_PATH"] = str(DB_PATH)
os.environ["PROPOSER_ID"] = proposer_id

# Ensure data directory
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Optionally initialize genesis if DB doesn't exist
if not DB_PATH.exists():
    print("[*] Database not found. Initializing production genesis...")
    result = subprocess.run(
        [
            sys.executable,
            "/opt/aitbc/scripts/utils/init_production_genesis.py",
            "--chain-id",
            CHAIN_ID,
            "--db-path",
            str(DB_PATH),
        ],
        check=False,
    )
    if result.returncode != 0:
        print("[!] Genesis initialization failed. Aborting.")
        sys.exit(1)

# Start the node
print(f"[*] Starting blockchain node for chain {CHAIN_ID}...")
# Change to the blockchain-node directory (since .env and uvicorn expect relative paths)
os.chdir("/opt/aitbc/apps/blockchain-node")
# Use the virtualenv Python
venv_python = Path("/opt/aitbc/apps/blockchain-node/.venv/bin/python")
if not venv_python.exists():
    print(f"[!] Virtualenv not found at {venv_python}")
    sys.exit(1)

# Exec uvicorn
os.execv(str(venv_python), [str(venv_python), "-m", "uvicorn", "aitbc_chain.app:app", "--host", "127.0.0.1", "--port", "8006"])
