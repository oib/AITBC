#!/usr/bin/env python3
"""
Production launcher for AITBC blockchain node.
Sets up environment, initializes genesis if needed, and starts the node.
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

# Configuration
CHAIN_ID = "ait-mainnet"
DATA_DIR = Path("/var/lib/aitbc/data/ait-mainnet")
DB_PATH = DATA_DIR / "chain.db"
KEYS_DIR = Path("/var/lib/aitbc/keystore")

# Check for proposer key in keystore
PROPOSER_KEY_FILE = KEYS_DIR / "aitbc1genesis.json"
if not PROPOSER_KEY_FILE.exists():
    print(f"[!] Proposer keystore not found at {PROPOSER_KEY_FILE}")
    print("    Run scripts/keystore.py to generate it first.")
    sys.exit(1)

# Set environment variables
os.environ["CHAIN_ID"] = CHAIN_ID
os.environ["SUPPORTED_CHAINS"] = CHAIN_ID
os.environ["DB_PATH"] = str(DB_PATH)
os.environ["PROPOSER_ID"] = "aitbc1genesis"
# PROPOSER_KEY will be read from keystore by the node? Currently .env expects hex directly.
# We can read the keystore, decrypt, and set PROPOSER_KEY, but the node doesn't support that out of box.
# So we require that PROPOSER_KEY is set in .env file manually after key generation.
# This script will check for PROPOSER_KEY env var or fail with instructions.
if not os.getenv("PROPOSER_KEY"):
    print("[!] PROPOSER_KEY environment variable not set.")
    print("    Please edit /opt/aitbc/apps/blockchain-node/.env and set PROPOSER_KEY to the hex private key of aitbc1genesis.")
    sys.exit(1)

# Ensure data directory
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Optionally initialize genesis if DB doesn't exist
if not DB_PATH.exists():
    print("[*] Database not found. Initializing production genesis...")
    result = subprocess.run([
        sys.executable,
        "/opt/aitbc/scripts/init_production_genesis.py",
        "--chain-id", CHAIN_ID,
        "--db-path", str(DB_PATH)
    ], check=False)
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
