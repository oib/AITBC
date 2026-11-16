#!/usr/bin/env python3
"""Key/custody phase cluster for the bc-2 dress-rehearsal harness.

Split out of ``rehearsal.py`` (issue #1860 Phase 2): everything that mints,
stores, loads or custody-checks the rehearsal keyset plus the genesis chain
constants and allocation/parameter/validator derivations built from it.
``rehearsal.py`` re-imports every name here, so ``import rehearsal`` exposes
the same surface as before.

Nothing here touches a live unit, env file, port, data dir, wallet or
keystore. Rehearsal keys are minted fresh inside the scratch root and
deleted with it — never copied from or derived from fleet material.
"""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "apps" / "blockchain-node" / "src"), str(REPO_ROOT / "cli")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# Local copy of rehearsal._fail: rehearsal.py imports this module, so this
# module cannot import back without a cycle.
def _fail(msg: str) -> SystemExit:
    print(f"[!] {msg}", file=sys.stderr)
    return SystemExit(1)


CHAIN_ID = "bc-2"
N_PROPOSERS = 4
N_INSTANCES = 5  # 4 proposers + 1 follower
STAKE_PER_VALIDATOR = "1000"

# Treasury: 100,000,000 AIT at UNITS_PER_AIT=36,000,000. Working floats: 256 AIT
# on top (operator-labelled working figures, tuned at dress rehearsal).
UNITS_PER_AIT = 36_000_000
TREASURY_UNITS = 100_000_000 * UNITS_PER_AIT
WORKING_UNITS = 256 * UNITS_PER_AIT
EXPECTED_TOTAL_UNITS = TREASURY_UNITS + WORKING_UNITS

# 11 named service floats at 1 AIT each (retired wallets get 0); the rest of
# the working band sits on one ops float, operator-adjustable at rehearsal.
SERVICE_FLOAT_NAMES = [
    "aiengine",
    "market-service",
    "coordinator-service",
    "trading-service",
    "exchange-service",
    "agent-coordinator",
    "pool-hub",
    "gpu-service",
    "edge-service",
    "ait-sell-escrow",
    "bridge-monitor",
]
SERVICE_FLOAT_UNITS = 1 * UNITS_PER_AIT
# Funded at 1 AIT: the 11 named floats + 2 executors + 3 authorities = 16
# accounts; the ops float holds the remainder of the 256 AIT working band.
N_SMALL_FLOATS = len(SERVICE_FLOAT_NAMES) + 2 + 3
OPS_FLOAT_UNITS = WORKING_UNITS - N_SMALL_FLOATS * SERVICE_FLOAT_UNITS


def _mint_key() -> dict[str, str]:
    """Rehearsal-only keypair via eth-account; stays inside the scratch root."""
    from eth_account import Account
    from eth_keys import keys as eth_keys

    account = Account.create(secrets.token_bytes(32))
    private = eth_keys.PrivateKey(bytes(account.key))
    return {
        "address": account.address,
        "private_key": account.key.hex(),
        # eth_keys' to_hex() already carries the 0x prefix.
        "public_key": private.public_key.to_hex(),
    }


def phase_keys(root: Path) -> Path:
    key_dir = root / "keystore"
    key_file = key_dir / "keys.json"
    if key_file.exists():
        raise _fail(f"{key_file} exists — teardown first (refusing to overwrite rehearsal keys)")
    key_dir.mkdir(parents=True)
    keys = {
        "proposers": [_mint_key() for _ in range(N_PROPOSERS)],
        "executors": [_mint_key() for _ in range(2)],
        "authorities": {name: _mint_key() for name in ("bond_slash", "bridge_release", "escrow_settlement")},
        "treasury": _mint_key(),
        "service_floats": {name: _mint_key() for name in SERVICE_FLOAT_NAMES},
        "ops_float": _mint_key(),
    }
    key_file.write_text(json.dumps(keys, indent=2))
    key_file.chmod(0o600)
    print(f"[+] minted rehearsal keys -> {key_file} (0600; deleted with the scratch tree)")
    return key_file


def _load_keys(root: Path) -> dict:
    key_file = root / "keystore" / "keys.json"
    if not key_file.exists():
        raise _fail(f"no rehearsal keys at {key_file} — run `rehearsal.py keys` first")
    return json.loads(key_file.read_text())


def _bond_account_addresses() -> list[str]:
    """The two zero-balance accounts ``init_db`` always creates
    (``ensure_bond_accounts``): bond escrow + bond burn, keccak-derived.
    The genesis loader skips already-existing rows, so these must appear in
    the allocation file at balance 0 — the claim then covers every row the
    post-init account table will ever contain."""
    from eth_utils import keccak

    from aitbc_chain.base_models import canonical_address

    return [
        canonical_address("0x" + keccak(b"aitbc.bond.escrow").hex()[:40]),
        canonical_address("0x" + keccak(b"aitbc.bond.burn").hex()[:40]),
    ]


def _allocations(keys: dict) -> list[dict]:
    """Working allocation figures (operator-labelled, tuned at dress rehearsal)."""
    allocs = [{"address": keys["treasury"]["address"], "balance": TREASURY_UNITS, "nonce": 0}]
    funded = [
        *(k["address"] for k in keys["executors"]),
        *(k["address"] for k in keys["authorities"].values()),
        *(k["address"] for k in keys["service_floats"].values()),
    ]
    for addr in funded:
        allocs.append({"address": addr, "balance": SERVICE_FLOAT_UNITS, "nonce": 0})
    allocs.append({"address": keys["ops_float"]["address"], "balance": OPS_FLOAT_UNITS, "nonce": 0})
    for addr in _bond_account_addresses():
        allocs.append({"address": addr, "balance": 0, "nonce": 0})
    return allocs


def _parameters(keys: dict) -> dict[str, str]:
    auth = keys["authorities"]
    executors = ",".join(k["address"] for k in keys["executors"])
    return {
        "governance_executors": executors,
        "escrow_settlement_authority": auth["escrow_settlement"]["address"],
        "bond_slash_authority": auth["bond_slash"]["address"],
        "bridge_release_authority": auth["bridge_release"]["address"],
        "escrow_fee_recipient": auth["escrow_settlement"]["address"],
    }


def _bridge_validators(keys: dict) -> list[dict]:
    return [{"address": k["address"], "public_key": k["public_key"], "epoch": 1} for k in keys["proposers"]]


# Genesis chain parameters whose values name authority addresses.
# ``governance_executors`` is a comma-separated address list; the rest are
# single addresses. Every address baked under these names must have its
# private key in the keystore before height 1 seals.
AUTHORITY_PARAMETERS = (
    "governance_executors",
    "bond_slash_authority",
    "bridge_release_authority",
    "escrow_settlement_authority",
)


def _keystore_private_keys(keys: dict) -> dict[str, str]:
    """lowercased address -> private_key for every ``{address, private_key}``
    entry anywhere in the keystore structure (top-level dicts and lists)."""
    found: dict[str, str] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            addr = node.get("address")
            if isinstance(addr, str) and addr.strip():
                found[addr.strip().lower()] = str(node.get("private_key") or "").strip()
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(keys)
    return found


def _check_authority_custody(root: Path, genesis: Path | None = None) -> None:
    """Refuse unless every authority address baked into the genesis
    parameters has a private key recorded in ``keystore/keys.json`` — the
    mechanical guard against the bc-2 incident, where the baked
    ``governance_executors`` had no recorded keys and GOVERNANCE_EXECUTE is
    unexercisable. Runs inside ``phase_genesis`` after the artifact verifies
    (before height 1 can seal) and standalone as the ``custody`` subcommand."""
    genesis = genesis or root / "genesis-build" / "out" / "data" / CHAIN_ID / "genesis.json"
    key_file = root / "keystore" / "keys.json"
    if not genesis.exists():
        raise _fail(f"no built genesis at {genesis} — run `rehearsal.py genesis` first")
    keys = _load_keys(root)  # fails with the right message when keys.json is absent
    parameters = json.loads(genesis.read_text()).get("parameters") or {}
    if not isinstance(parameters, dict):
        raise _fail(f"{genesis} carries a non-object parameters field")
    have = _keystore_private_keys(keys)
    missing, n = _custody_misses(parameters, have)
    if missing:
        raise _fail(f"genesis authority custody missing from {key_file}:\n  - " + "\n  - ".join(missing))
    print(f"[+] authority custody: {n} genesis authority addresses have verified private keys in keystore/keys.json")


def _custody_misses(parameters: dict, have: dict[str, str]) -> tuple[list[str], int]:
    """(missing descriptions, checked count): one entry per baked authority
    address whose keystore private key is absent, empty, malformed or
    derives a different address."""
    missing: list[str] = []
    n = 0
    for name in AUTHORITY_PARAMETERS:
        for addr in (a.strip() for a in str(parameters.get(name) or "").split(",")):
            if not addr:
                continue
            n += 1
            pk = have.get(addr.lower())
            if pk is None:
                missing.append(f"{name} {addr}: no entry in keystore")
            elif not pk:
                missing.append(f"{name} {addr}: keystore entry has no private_key")
            else:
                derived = _derive_key_address(pk)
                if derived is None:
                    missing.append(f"{name} {addr}: keystore private_key is malformed (not a valid secret)")
                elif derived != addr.lower():
                    missing.append(f"{name} {addr}: keystore private_key derives {derived} — custody of a different address")
    return missing, n


def _derive_key_address(private_key: str) -> str | None:
    """The lowercased address ``private_key`` controls, or None when the
    string is not a parseable secp256k1 secret. The custody gate's proof:
    a recorded key that does not derive the baked address is no custody —
    the bc-2 executors had *no* recorded keys; a hand-assembled keystore
    can instead hold the *wrong* key and read identically."""
    from eth_account import Account

    try:
        return Account.from_key(private_key).address.lower()
    except (TypeError, ValueError):
        return None
