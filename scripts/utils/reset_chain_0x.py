#!/usr/bin/env python3
"""Reset the AITBC chain for the canonical 0x address migration.

This is an operational helper. Run it on the proposer/hub node after migrating
environment and wallet files to 0x addresses. It backs up the existing chain
data, creates a fresh genesis block and allocations, computes the state root,
and writes a `genesis.json` that followers can bootstrap from.

Typical usage from the repo root:

    CHAIN_ID=ait-localnet DB_PATH=/var/lib/aitbc/data/ait-localnet/chain.db \
    PYTHONPATH=/opt/aitbc:/opt/aitbc/apps/blockchain-node/src \
    python3 scripts/utils/reset_chain_0x.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, UTC
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "blockchain-node" / "src"))

from aitbc.utils import reset_guard
from aitbc.utils.genesis_accounts import (
    SERVICE_ACCOUNT_NAMES,
    derived_key_error,
    find_derived,
    new_account,
)
from aitbc.utils.units import ait_to_units
from aitbc_chain.config import ChainSettings
from aitbc_chain.database import init_db, session_scope
from aitbc_chain.base_models import Account, Block
from aitbc_chain.genesis_builder import GenesisBuildError, build_genesis_doc, empty_bridge_root
from aitbc.crypto.signature_recovery import canonical_address


def _service_keys_file() -> Path:
    return Path(os.environ.get("AITBC_SERVICE_KEYS_FILE", "/var/lib/aitbc/keystore/service_accounts.json"))


ALLOW_DERIVED_ENV = "AITBC_ALLOW_DERIVED_GENESIS"

GENESIS_TIMESTAMP = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)


def _service_accounts(keys_file: Path) -> dict[str, str]:
    """Return {name: address} for the pre-funded service accounts.

    Reuses ``keys_file`` when it already exists so that re-running this script
    does not strand the balance of a previous run at keys nobody kept. Otherwise
    mints a fresh keypair per account and writes the keys out at 0600 -- the
    same custody the genesis and treasury keys get in setup_production.py.
    """
    if keys_file.exists():
        stored = json.loads(keys_file.read_text())
        print(f"[*] Reusing service account keys from {keys_file}")
        return {name: entry["address"] for name, entry in stored.items()}

    minted = {}
    for name in SERVICE_ACCOUNT_NAMES:
        private_hex, address = new_account()
        minted[name] = {"address": address, "private_key": "0x" + private_hex}
    keys_file.parent.mkdir(parents=True, exist_ok=True)
    keys_file.write_text(json.dumps(minted, indent=2))
    os.chmod(keys_file, 0o600)
    print(f"[+] Minted {len(minted)} service account keys -> {keys_file} (0600, back this up)")
    return {name: entry["address"] for name, entry in minted.items()}


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def _wallet_addresses(wallet_dir: Path) -> set[str]:
    addrs: set[str] = set()
    for p in wallet_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text())
            addr = data.get("address")
            if addr:
                addrs.add(str(addr))
        except Exception:
            pass
    return addrs


def _build_allocations(
    node_env: dict[str, str],
    blockchain_env: dict[str, str],
    genesis_address: str,
    wallets: set[str],
) -> list[dict[str, object]]:
    """Assemble genesis allocations: genesis, wallets, fee-payers, service accounts."""
    # Ensure service accounts have enough balance to pay fees on the first blocks.
    service_balances: dict[str, int] = {}
    escrow_release = node_env.get("ESCROW_RELEASE_ADDRESS", "")
    agent_operator = node_env.get("AGENT_ECONOMICS_OPERATOR_ADDRESS") or blockchain_env.get(
        "AGENT_ECONOMICS_OPERATOR_ADDRESS", ""
    )
    for addr, amount in [(escrow_release, ait_to_units(5000)), (agent_operator, ait_to_units(5000))]:
        if addr and addr not in {genesis_address} | wallets:
            service_balances[addr] = amount

    allocations: list[dict[str, object]] = [{"address": genesis_address, "balance": ait_to_units(1_000_000_000), "nonce": 0}]
    for addr in sorted(wallets):
        allocations.append({"address": addr, "balance": ait_to_units(1_000_000), "nonce": 0})
    for addr, balance in sorted(service_balances.items()):
        allocations.append({"address": addr, "balance": balance, "nonce": 0})
    for _name, addr in sorted(_service_accounts(_service_keys_file()).items()):
        allocations.append({"address": addr, "balance": ait_to_units(1_000_000), "nonce": 0})
    return allocations


def _seed_chain_db(chain_id: str, genesis_doc: dict) -> None:
    """Insert accounts and block 0 exactly as the loader builds them from genesis.json.

    The block row mirrors ``poa._ensure_genesis_block``: proposer ``genesis``,
    the document's ``genesis_hash``/``state_root``/``timestamp``, the empty
    bridge trie root and the allocations in ``block_metadata``.
    """
    allocations = genesis_doc["allocations"]
    timestamp = datetime.fromisoformat(genesis_doc["timestamp"])

    with session_scope() as session:
        for alloc in allocations:
            session.add(
                Account(
                    chain_id=chain_id,
                    address=alloc["address"],
                    balance=alloc["balance"],
                    nonce=int(alloc.get("nonce", 0)),
                )
            )
        session.add(
            Block(
                chain_id=chain_id,
                height=0,
                hash=genesis_doc["genesis_hash"],
                parent_hash="0x00",
                proposer="genesis",
                timestamp=timestamp,
                tx_count=0,
                state_root=genesis_doc["state_root"],
                bridge_state_root=empty_bridge_root(),
                block_metadata=json.dumps({"allocations": allocations}),
            )
        )
        session.commit()
        print(f"[+] Created block 0: {genesis_doc['genesis_hash']}")
        print(f"[+] State root: {genesis_doc['state_root']}")


def main() -> int:
    from aitbc.utils.chain_id import resolve_chain_id

    chain_id = resolve_chain_id()
    db_path = Path(os.environ.get("DB_PATH", f"/var/lib/aitbc/data/{chain_id}/chain.db"))
    data_dir = db_path.parent
    genesis_json = data_dir / "genesis.json"

    # Scratch-only reset guard: this tool rewrites a chain DB and reads env
    # files, wallet files, and the service-account keystore. Every one of
    # those paths must resolve under AITBC_RESET_SCRATCH — the defaults below
    # are live paths, so an unset marker refuses before anything is touched.
    etc_dir = Path(os.environ.get("AITBC_ETC_DIR", "/etc/aitbc"))
    wallets_dir = Path(os.environ.get("AITBC_WALLETS_DIR", "/var/lib/aitbc/wallets"))
    service_keys = _service_keys_file()
    genesis_prod = Path(os.environ.get("GENESIS_YAML_OUT", "/opt/aitbc/genesis_prod.yaml"))
    try:
        reset_guard.assert_scratch_targets(db_path, genesis_json, etc_dir, wallets_dir, service_keys, genesis_prod)
        reset_guard.assert_data_dir_env()
        reset_guard.assert_not_live_chain(chain_id)
    except reset_guard.ResetGuardError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1

    node_env = _load_env(etc_dir / "node.env")
    blockchain_env = _load_env(etc_dir / "blockchain.env")
    genesis_address = node_env.get("GENESIS_ADDRESS") or blockchain_env.get("GENESIS_WALLET_ADDRESS") or ""

    if not genesis_address:
        print("[!] GENESIS_ADDRESS not found in env", file=sys.stderr)
        return 1

    wallets = _wallet_addresses(wallets_dir)
    wallets.discard(genesis_address)

    allocations = _build_allocations(node_env, blockchain_env, genesis_address, wallets)

    # Last gate before anything is committed. Catches a derivable address from
    # any source -- a minted set is clean by construction, but wallets/ and the
    # env-supplied addresses above are not under this script's control.
    derived = find_derived(str(a["address"]) for a in allocations)
    if derived and os.environ.get(ALLOW_DERIVED_ENV) != "1":
        print("[!] " + derived_key_error(derived, override=ALLOW_DERIVED_ENV), file=sys.stderr)
        return 1

    # Canonical EIP-55 spelling and the loader-valid document in one step:
    # build_genesis_doc recomputes state_root and genesis_hash with the same
    # code the node's _verify_genesis_claims runs, so the file it emits is
    # bootstrap-able by construction.
    try:
        for alloc in allocations:
            alloc["address"] = canonical_address(str(alloc["address"]), strict=True)
        genesis_doc = build_genesis_doc(
            chain_id=chain_id,
            allocations=allocations,
            timestamp=GENESIS_TIMESTAMP.isoformat(),
        )
    except (ValueError, GenesisBuildError) as exc:
        print(f"[!] genesis document refused: {exc}", file=sys.stderr)
        return 1

    if data_dir.exists():
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup = data_dir.with_name(f"{data_dir.name}-pre-0x-migration-{ts}")
        shutil.move(str(data_dir), str(backup))
        print(f"[+] Backed up old chain to {backup}")

    data_dir.mkdir(parents=True, exist_ok=True)

    genesis_prod.parent.mkdir(parents=True, exist_ok=True)
    genesis_prod.write_text(yaml.safe_dump({"genesis": {"accounts": allocations}}, sort_keys=False))
    os.chmod(genesis_prod, 0o600)
    print(f"[+] Wrote {genesis_prod}")

    os.environ["CHAIN_ID"] = chain_id
    os.environ["DB_PATH"] = str(db_path)
    settings = ChainSettings()
    print(f"[*] DB path: {settings.db_path}")

    init_db()
    print("[+] Database initialized")

    _seed_chain_db(chain_id, genesis_doc)

    genesis_json.write_text(json.dumps(genesis_doc, indent=2))
    os.chmod(genesis_json, 0o644)
    print(f"[+] Wrote {genesis_json}")
    print("[+] Done. Start the blockchain node to begin block production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
