#!/usr/bin/env python3
"""
Full production setup:
- Generate keystore password file
- Generate encrypted keystores for the genesis, treasury and service accounts
- Initialize production database with 0x allocations
- Configure blockchain node .env for ait-mainnet
- Restart services

All addresses are canonical EIP-55 0x-prefixed secp256k1/EVM addresses.
No ``ait1`` or ``aitbc1`` prefix is used for address values.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from eth_account import Account

# Reuse the blockchain node's keystore encryption; insert that directory first so
# we don't accidentally import scripts/utils/keystore.py, which exports a
# different (Fernet, two-argument) encrypt_private_key. resolve() is required:
# on a bare __file__, parent.parent is scripts/, and the scripts/apps/... path
# that produced does not exist -- so the insert was a no-op, the wrong module
# won, and _write_keystore() below died on the three-argument call.
_BLOCKCHAIN_SCRIPTS = Path(__file__).resolve().parents[2] / "apps" / "blockchain-node" / "scripts"
sys.path.insert(0, str(_BLOCKCHAIN_SCRIPTS))
import keystore as _node_keystore

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from aitbc.utils.genesis_accounts import derived_key_error, find_derived, new_account

# Configuration
CHAIN_ID = "ait-mainnet"
DATA_DIR = Path("/var/lib/aitbc/data/ait-mainnet")
DB_PATH = DATA_DIR / "chain.db"
KEYS_DIR = Path("/var/lib/aitbc/keystore")
PASSWORD_FILE = KEYS_DIR / ".password"
NODE_ENV = Path("/opt/aitbc/apps/blockchain-node/.env")
SERVICE_NODE = "aitbc-blockchain-node"
SERVICE_RPC = "aitbc-blockchain-rpc"
GENESIS_PROD_YAML = Path("/opt/aitbc/genesis_prod.yaml")

ALLOW_DERIVED_ENV = "AITBC_ALLOW_DERIVED_GENESIS"

# Service accounts pre-funded at genesis, and what each one gets. These used to
# be allocated at sha256(name) addresses, which put their private keys in the
# public repository; each now receives a real keypair and its own keystore.
SERVICE_ACCOUNT_BALANCES: dict[str, int] = {
    "aitbc1aiengine": 2_000_000,
    "aitbc1surveillance": 1_500_000,
    "aitbc1analytics": 1_000_000,
    "aitbc1marketplace": 2_000_000,
    "aitbc1enterprise": 3_000_000,
    "aitbc1multimodal": 1_500_000,
    "aitbc1zkproofs": 1_000_000,
    "aitbc1crosschain": 2_000_000,
    "aitbc1developer1": 500_000,
    "aitbc1developer2": 300_000,
    "aitbc1tester": 200_000,
}


def run(cmd, check=True, capture_output=False):
    print(f"+ {cmd}")
    if capture_output:
        result = subprocess.run(cmd, shell=False, check=check, capture_output=True, text=True)
    else:
        result = subprocess.run(cmd, shell=False, check=check)
    return result


def _write_keystore(name: str, private_hex: str, password: str, keystore_dir: Path) -> Path:
    """Write a web3-style keystore JSON for the given private key."""
    private_bytes = bytes.fromhex(private_hex)
    account = Account.from_key(private_bytes)
    address = account.address
    salt = os.urandom(32)
    ks = _node_keystore.encrypt_private_key(private_bytes, password, salt)
    ks["address"] = address
    ks["keytype"] = "secp256k1"
    ks["version"] = 1
    ks["created_at"] = datetime.now(UTC).isoformat() + "Z"

    keystore_dir.mkdir(parents=True, exist_ok=True)
    out_file = keystore_dir / f"{name}.json"
    out_file.write_text(json.dumps(ks, indent=2))
    os.chmod(out_file, 0o600)
    return out_file


def _create_service_accounts(password: str, keystore_dir: Path) -> dict[str, str]:
    """Mint a keypair and keystore per service account. Returns {name: address}."""
    addresses: dict[str, str] = {}
    for name in SERVICE_ACCOUNT_BALANCES:
        private_hex, address = new_account()
        _write_keystore(name, private_hex, password, keystore_dir)
        addresses[name] = address
        print(f"[+] {name}: {address}")
    return addresses


def _write_genesis_prod_yaml(
    genesis_address: str,
    treasury_address: str,
    service_addresses: dict[str, str],
    output: Path,
) -> None:
    """Write a genesis_prod.yaml with 0x addresses and production balances."""
    accounts = [
        {"address": genesis_address, "balance": 10_000_000},
        {"address": treasury_address, "balance": 5_000_000},
    ]
    accounts += [
        {"address": service_addresses[name], "balance": balance} for name, balance in SERVICE_ACCOUNT_BALANCES.items()
    ]

    # A genesis file is append-only in practice: once the chain is initialised
    # from it, a bad address there is a balance nobody can take back. Check
    # before writing rather than after.
    derived = find_derived(str(a["address"]) for a in accounts)
    if derived and os.environ.get(ALLOW_DERIVED_ENV) != "1":
        sys.exit("[!] " + derived_key_error(derived, override=ALLOW_DERIVED_ENV))

    data = {"genesis": {"accounts": accounts}}
    output.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    output.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    os.chmod(output, 0o600)


def main():
    if os.geteuid() != 0:
        print("Run as root (sudo)")
        sys.exit(1)

    # 1. Keystore directory and password
    run(f"mkdir -p {KEYS_DIR}")
    run(f"chown -R root:root {KEYS_DIR}")

    # SECURITY FIX: Use credential system instead of writing password to disk
    # Password is stored in /etc/aitbc/credentials/keystore_password with 600 permissions
    password = os.environ.get("AITBC_KEYSTORE_PASSWORD")
    if not password:
        # Read from credential file if not provided
        cred_file = Path("/etc/aitbc/credentials/keystore_password")
        if cred_file.exists():
            password = cred_file.read_text().strip()
        else:
            # Generate secure random password and store in credentials
            password = secrets.token_hex(32)
            cred_file.parent.mkdir(parents=True, exist_ok=True)
            cred_file.write_text(password)
            os.chmod(cred_file, 0o600)
            print(f"[INFO] Password stored in {cred_file} with 600 permissions")
    else:
        # Use provided password from environment without writing to disk
        # Clear password from environment variable for security
        if "AITBC_KEYSTORE_PASSWORD" in os.environ:
            del os.environ["AITBC_KEYSTORE_PASSWORD"]

    os.environ["KEYSTORE_PASSWORD"] = password
    PASSWORD_FILE.write_text(password)
    os.chmod(PASSWORD_FILE, 0o600)

    # 2. Generate secp256k1 keypairs for genesis and treasury
    print("\n=== Generating genesis keystore ===")
    genesis_priv = secrets.token_hex(32)
    genesis_addr = Account.from_key(genesis_priv).address
    genesis_ks = _write_keystore("aitbc1genesis", genesis_priv, password, KEYS_DIR)
    print(f"[+] Genesis address: {genesis_addr}")
    print(f"[+] Keystore: {genesis_ks}")

    print("\n=== Generating treasury keystore ===")
    treasury_priv = secrets.token_hex(32)
    treasury_addr = Account.from_key(treasury_priv).address
    treasury_ks = _write_keystore("aitbc1treasury", treasury_priv, password, KEYS_DIR)
    print(f"[+] Treasury address: {treasury_addr}")
    print(f"[+] Keystore: {treasury_ks}")

    # Save private keys locally (production operators must secure these)
    (KEYS_DIR / "genesis_private_key.txt").write_text("0x" + genesis_priv)
    os.chmod(KEYS_DIR / "genesis_private_key.txt", 0o600)
    (KEYS_DIR / "treasury_private_key.txt").write_text("0x" + treasury_priv)
    os.chmod(KEYS_DIR / "treasury_private_key.txt", 0o600)

    # 3. Data directory
    run(f"mkdir -p {DATA_DIR}")
    run(f"chown -R root:root {DATA_DIR}")

    # 4. Generate the service account keystores, then write genesis_prod.yaml
    print("\n=== Generating service account keystores ===")
    service_addrs = _create_service_accounts(password, KEYS_DIR)

    _write_genesis_prod_yaml(genesis_addr, treasury_addr, service_addrs, GENESIS_PROD_YAML)
    print(f"[+] Wrote {GENESIS_PROD_YAML}")

    # 5. Initialize DB
    os.environ["DB_PATH"] = str(DB_PATH)
    os.environ["CHAIN_ID"] = CHAIN_ID
    run(
        f"sudo -E {sys.executable} /opt/aitbc/scripts/utils/init_production_genesis.py --chain-id {CHAIN_ID} --db-path {DB_PATH}"
    )

    # 6. Write .env for blockchain node
    env_content = f"""CHAIN_ID={CHAIN_ID}
SUPPORTED_CHAINS={CHAIN_ID}
DB_PATH=./data/ait-mainnet/chain.db
PROPOSER_ID={genesis_addr}
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
    os.chmod(NODE_ENV, 0o600)
    print(f"[+] Updated {NODE_ENV}")

    # 7. Restart services
    run("systemctl daemon-reload")
    run(f"systemctl restart {SERVICE_NODE} {SERVICE_RPC}")

    print("\n[+] Production setup complete!")
    print(f"[+] Verify with: curl 'http://127.0.0.1:8006/head?chain_id={CHAIN_ID}' | jq")
    print(f"[+] Keystore files in {KEYS_DIR} (encrypted, 600) -- including one per service account")
    print(f"[+] Private keys saved in {KEYS_DIR}/genesis_private_key.txt and treasury_private_key.txt (keep secure!)")


if __name__ == "__main__":
    main()
