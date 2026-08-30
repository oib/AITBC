#!/usr/bin/env python3
"""Register bridge validators across AITBC nodes without printing key material.

This script reads private keys from env files (e.g. ``/etc/aitbc/node.env`` and a
dedicated ``/etc/aitbc/bridge-validator-keys.env``), derives public keys and
addresses, signs the registration payload, and POSTs it to the bridge
``/bridge/validators/register`` RPC endpoint on each supplied node.

No private key value is ever written to stdout, stderr, or the command line.
The script exits with a non-zero status if any registration fails.

Typical usage::

    source /opt/aitbc/venv/bin/activate
    python3 /opt/aitbc/scripts/ops/register_bridge_validators.py \
        --env-file /etc/aitbc/node.env \
        --env-file /etc/aitbc/bridge-validator-keys.env \
        --chain-id ait-hub.aitbc.bubuit.net \
        --rpc-url http://127.0.0.1:8202/rpc \
        --rpc-url http://aitbc1:8202/rpc \
        --rpc-url http://aitbc3:8202/rpc

The extra env file should contain the admin key and one or more validator keys::

    BRIDGE_ADMIN_PRIVATE_KEY_SOURCE=PROPOSER_KEY
    BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1=PROPOSER_KEY
    BRIDGE_VALIDATOR_PRIVATE_KEY_2=0x...
    BRIDGE_RPC_URLS=http://127.0.0.1:8202/rpc,http://aitbc1:8202/rpc

If ``BRIDGE_ADMIN_PRIVATE_KEY_SOURCE`` is set, the script reads the admin key from
that environment variable name (e.g. ``PROPOSER_KEY`` or ``GENESIS_PRIVATE_KEY``).
Alternatively set ``BRIDGE_ADMIN_PRIVATE_KEY`` to a literal hex value.

Validator private keys can be supplied similarly with either:
  - ``BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_<N>`` referencing an env var name
  - ``BRIDGE_VALIDATOR_PRIVATE_KEY_<N>`` as a literal hex value

The script stops numbering at the first missing ``_<N>`` key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _warn(msg: str) -> None:
    print(f"WARNING: {msg}", file=sys.stderr)


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _load_env_file(path: str) -> None:
    """Load KEY=VALUE lines from a file into os.environ.

    Values are not expanded or quoted. Lines beginning with ``#`` or empty lines
    are ignored. Values may be JSON or comma-separated strings.
    """
    p = Path(path)
    if not p.is_file():
        _warn(f"env file not found: {path}")
        return

    for line in p.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ[key.strip()] = value.strip()


def _get_admin_private_key() -> str:
    """Return the admin private key, reading from a referenced env var if needed."""
    literal = os.environ.get("BRIDGE_ADMIN_PRIVATE_KEY", "").strip()
    if literal:
        return literal.removeprefix("0x")

    source_var = os.environ.get("BRIDGE_ADMIN_PRIVATE_KEY_SOURCE", "").strip()
    if source_var:
        if source_var not in os.environ:
            _die(f"admin private key source env var {source_var!r} is not set")
        return os.environ[source_var].strip().removeprefix("0x")

    # Sensible fallbacks for the canonical hub admin (proposer / genesis).
    for fallback in ("PROPOSER_KEY", "GENESIS_PRIVATE_KEY"):
        if os.environ.get(fallback, "").strip():
            return os.environ[fallback].strip().removeprefix("0x")

    _die(
        "no admin private key found. Set BRIDGE_ADMIN_PRIVATE_KEY, "
        "BRIDGE_ADMIN_PRIVATE_KEY_SOURCE, PROPOSER_KEY, or GENESIS_PRIVATE_KEY."
    )


def _collect_validator_private_keys() -> list[tuple[str, str]]:
    """Collect validator private keys from BRIDGE_VALIDATOR_PRIVATE_KEY(_SOURCE)_<N>."""
    validators: list[tuple[str, str]] = []
    n = 1
    while True:
        source_var = f"BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_{n}"
        literal_var = f"BRIDGE_VALIDATOR_PRIVATE_KEY_{n}"

        literal = os.environ.get(literal_var, "").strip()
        source = os.environ.get(source_var, "").strip()

        if not literal and not source:
            break

        key: str
        if literal:
            key = literal.removeprefix("0x")
        else:
            if source not in os.environ:
                _die(f"validator {n} private key source env var {source!r} is not set")
            key = os.environ[source].strip().removeprefix("0x")

        validators.append((f"validator-{n}", key))
        n += 1

    if not validators:
        _die(
            "no validator private keys found. Set BRIDGE_VALIDATOR_PRIVATE_KEY_1 "
            "or BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1 (and increment for more)."
        )

    return validators


def _derive_address_and_public_key(private_key_hex: str) -> tuple[str, str]:
    """Derive the 0x-checksummed address and the 0x public key from a private key."""
    try:
        from eth_keys import keys
    except ImportError as exc:
        _die(f"eth_keys is not available: {exc}. Run inside the project venv.")

    pk = keys.PrivateKey(bytes.fromhex(private_key_hex))
    address = str(pk.public_key.to_checksum_address())
    public_key = pk.public_key.to_hex()
    return address, public_key


def _canonical_json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def _sign_hash(private_key_hex: str, msg_hash: bytes) -> str:
    """Sign a keccak256 hash and return the 65-byte hex signature."""
    from eth_keys import keys

    pk = keys.PrivateKey(bytes.fromhex(private_key_hex))
    return pk.sign_msg_hash(msg_hash).to_hex()


def _sign_dict(private_key_hex: str, data: dict[str, Any]) -> str:
    """Sign the canonical JSON of a dict after keccak256 hashing."""
    from eth_utils import keccak

    return _sign_hash(private_key_hex, keccak(_canonical_json(data)))


def _post_registration(rpc_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST the signed payload to the bridge validator registration RPC."""
    import httpx

    url = rpc_url.rstrip("/") + "/bridge/validators/register"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload)
            try:
                return resp.json()
            except Exception:
                return {"success": resp.is_success, "error": resp.text, "status_code": resp.status_code}
    except httpx.HTTPError as exc:
        return {"success": False, "error": str(exc)}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Register bridge validators across AITBC nodes.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Path to a KEY=VALUE env file to load (may be repeated).",
    )
    parser.add_argument(
        "--chain-id",
        required=True,
        help="Chain ID to register validators for.",
    )
    parser.add_argument(
        "--rpc-url",
        action="append",
        default=[],
        help="Base RPC URL to POST to (e.g. http://127.0.0.1:8202/rpc). May be repeated.",
    )
    parser.add_argument(
        "--epoch",
        type=int,
        default=0,
        help="Validator epoch number (default: 0).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the payloads without POSTing them.",
    )

    args = parser.parse_args()

    # Load env files first so all key lookups work.
    for env_path in args.env_file:
        _load_env_file(env_path)

    if not args.rpc_url:
        # Try a comma-separated env var, otherwise default to localhost.
        urls = os.environ.get("BRIDGE_RPC_URLS", "http://127.0.0.1:8202/rpc").split(",")
        args.rpc_url = [u.strip() for u in urls if u.strip()]

    admin_key = _get_admin_private_key()
    admin_address, _ = _derive_address_and_public_key(admin_key)

    validators = _collect_validator_private_keys()
    all_ok = True

    print(f"Admin address (derived): {admin_address}")
    print(f"Registering {len(validators)} validator(s) against {len(args.rpc_url)} RPC endpoint(s)")

    for name, validator_key in validators:
        address, public_key = _derive_address_and_public_key(validator_key)

        # Validator self-signature over the registration fields.
        self_sign_data = {
            "chain_id": args.chain_id,
            "address": address,
            "public_key": public_key,
            "action": "register",
        }
        self_signature = _sign_dict(validator_key, self_sign_data)

        # Build the full payload that the admin will co-sign.
        payload: dict[str, Any] = {
            "chain_id": args.chain_id,
            "address": address,
            "public_key": public_key,
            "signature": self_signature,
            "epoch": args.epoch,
            "admin_address": admin_address,
        }

        # Admin signature covers the payload excluding admin_signature itself.
        admin_signature = _sign_dict(admin_key, payload)
        payload["admin_signature"] = admin_signature

        if args.dry_run:
            print(f"[DRY-RUN] {name}: address={address}")
            continue

        for rpc_url in args.rpc_url:
            result = _post_registration(rpc_url, payload)
            status = result.get("success")
            if status:
                print(
                    f"OK  {name} @ {rpc_url}: {result.get('message', 'registered')} (address={result.get('address', address)})"
                )
            else:
                all_ok = False
                print(f"ERR {name} @ {rpc_url}: {result.get('error', 'unknown error')} (address={address})", file=sys.stderr)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(_main())
