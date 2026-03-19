#!/usr/bin/env python3
"""
Full production setup:
- Generate keystore password file
- Generate encrypted keystores for aitbc1genesis and aitbc1treasury
- Initialize production database with allocations
- Configure blockchain node .env for ait-mainnet
- Restart services
"""

import os
import subprocess
import sys
from pathlib import Path

# Configuration
CHAIN_ID = "ait-mainnet"
DATA_DIR = Path("/opt/aitbc/data/ait-mainnet")
DB_PATH = DATA_DIR / "chain.db"
KEYS_DIR = Path("/opt/aitbc/keystore")
PASSWORD_FILE = KEYS_DIR / ".password"
NODE_VENV = Path("/opt/aitbc/apps/blockchain-node/.venv/bin/python")
NODE_ENV = Path("/opt/aitbc/apps/blockchain-node/.env")
SERVICE_NODE = "aitbc-blockchain-node"
SERVICE_RPC = "aitbc-blockchain-rpc"

def run(cmd, check=True, capture_output=False):
    print(f"+ {cmd}")
    if capture_output:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
    else:
        result = subprocess.run(cmd, shell=True, check=check)
    return result

def main():
    if os.geteuid() != 0:
        print("Run as root (sudo)")
        sys.exit(1)

    # 1. Keystore directory and password
    run(f"mkdir -p {KEYS_DIR}")
    run(f"chown -R root:root {KEYS_DIR}")
    if not PASSWORD_FILE.exists():
        run(f"openssl rand -hex 32 > {PASSWORD_FILE}")
        run(f"chmod 600 {PASSWORD_FILE}")
    os.environ["KEYSTORE_PASSWORD"] = PASSWORD_FILE.read_text().strip()

    # 2. Generate keystores
    print("\n=== Generating keystore for aitbc1genesis ===")
    result = run(
        f"{NODE_VENV} /opt/aitbc/scripts/keystore.py aitbc1genesis --output-dir {KEYS_DIR} --force",
        capture_output=True
    )
    print(result.stdout)
    genesis_priv = None
    for line in result.stdout.splitlines():
        if "Private key (hex):" in line:
            genesis_priv = line.split(":",1)[1].strip()
            break
    if not genesis_priv:
        print("ERROR: Could not extract genesis private key")
        sys.exit(1)
    (KEYS_DIR / "genesis_private_key.txt").write_text(genesis_priv)
    os.chmod(KEYS_DIR / "genesis_private_key.txt", 0o600)

    print("\n=== Generating keystore for aitbc1treasury ===")
    result = run(
        f"{NODE_VENV} /opt/aitbc/scripts/keystore.py aitbc1treasury --output-dir {KEYS_DIR} --force",
        capture_output=True
    )
    print(result.stdout)
    treasury_priv = None
    for line in result.stdout.splitlines():
        if "Private key (hex):" in line:
            treasury_priv = line.split(":",1)[1].strip()
            break
    if not treasury_priv:
        print("ERROR: Could not extract treasury private key")
        sys.exit(1)
    (KEYS_DIR / "treasury_private_key.txt").write_text(treasury_priv)
    os.chmod(KEYS_DIR / "treasury_private_key.txt", 0o600)

    # 3. Data directory
    run(f"mkdir -p {DATA_DIR}")
    run(f"chown -R root:root {DATA_DIR}")

    # 4. Initialize DB
    os.environ["DB_PATH"] = str(DB_PATH)
    os.environ["CHAIN_ID"] = CHAIN_ID
    run(f"sudo -E {NODE_VENV} /opt/aitbc/scripts/init_production_genesis.py --chain-id {CHAIN_ID} --db-path {DB_PATH}")

    # 5. Write .env for blockchain node
    env_content = f"""CHAIN_ID={CHAIN_ID}
SUPPORTED_CHAINS={CHAIN_ID}
DB_PATH=./data/ait-mainnet/chain.db
PROPOSER_ID=aitbc1genesis
PROPOSER_KEY=0x{genesis_priv}
PROPOSER_INTERVAL_SECONDS=5
BLOCK_TIME_SECONDS=2

RPC_BIND_HOST=127.0.0.1
RPC_BIND_PORT=8006
P2P_BIND_HOST=127.0.0.2
P2P_BIND_PORT=8005

MEMPOOL_BACKEND=database
MIN_FEE=0
GOSSIP_BACKEND=memory
"""
    NODE_ENV.write_text(env_content)
    os.chmod(NODE_ENV, 0o644)
    print(f"[+] Updated {NODE_ENV}")

    # 6. Restart services
    run("systemctl daemon-reload")
    run(f"systemctl restart {SERVICE_NODE} {SERVICE_RPC}")

    print("\n[+] Production setup complete!")
    print(f"[+] Verify with: curl 'http://127.0.0.1:8006/head?chain_id={CHAIN_ID}' | jq")
    print(f"[+] Keystore files in {KEYS_DIR} (encrypted, 600)")
    print(f"[+] Private keys saved in {KEYS_DIR}/genesis_private_key.txt and treasury_private_key.txt (keep secure!)")

if __name__ == "__main__":
    main()
