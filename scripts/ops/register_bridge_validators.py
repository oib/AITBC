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
        --chain-id ait-localnet \
        --rpc-url http://127.0.0.1:8202/rpc \
        --rpc-url http://aitbc1:8202/rpc \
        --rpc-url http://aitbc3:8202/rpc

The extra env file should contain the admin key and one or more validator keys::

    BRIDGE_ADMIN_PRIVATE_KEY_SOURCE=PROPOSER_KEY
    BRIDGE_ADMIN_ADDRESS=0x...
    BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1=PROPOSER_KEY
    BRIDGE_VALIDATOR_ADDRESS_1=0x...
    BRIDGE_VALIDATOR_PRIVATE_KEY_2=0x...
    BRIDGE_RPC_URLS=http://127.0.0.1:8202/rpc,http://aitbc1:8202/rpc

The admin key resolves in this order (first match wins):

  - ``BRIDGE_ADMIN_PRIVATE_KEY`` — a literal hex value
  - ``BRIDGE_ADMIN_PRIVATE_KEY_FILE`` — a path to a file holding the hex key
    (e.g. the workstation-custody ``keys/bridge_admin.key``)
  - ``BRIDGE_ADMIN_PRIVATE_KEY_SOURCE`` — the *name* of an environment variable
    holding the key (e.g. ``PROPOSER_KEY`` or ``GENESIS_PRIVATE_KEY``)
  - fallbacks ``PROPOSER_KEY`` / ``GENESIS_PRIVATE_KEY``

Validator private keys can be supplied similarly with either:
  - ``BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_<N>`` referencing an env var name
  - ``BRIDGE_VALIDATOR_PRIVATE_KEY_<N>`` as a literal hex value

The script stops numbering at the first missing ``_<N>`` key.

A key read through an env var name is a different identity on every host:
``PROPOSER_KEY`` is hub's key on hub and node2's own validator key on node2, so the
same ``..._SOURCE_1=PROPOSER_KEY`` line registers a different validator depending on
where the script runs. Every key reached that way (including the admin fallback to
``PROPOSER_KEY``/``GENESIS_PRIVATE_KEY``) must therefore be bound to the address it
must have, via ``BRIDGE_ADMIN_ADDRESS`` / ``BRIDGE_VALIDATOR_ADDRESS_<N>``, with the
same value in the env file on every host. A host whose key derives a different address
stops with an error instead of registering the wrong identity. A literal or file key
needs no declaration, but one that is declared is enforced too. ``--dry-run`` performs
the same checks without POSTing anything.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from datetime import UTC, datetime
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


def _normalize_address(value: str) -> str:
    """Lower-case ``0x`` form, so checksummed and lower-case spellings compare equal."""
    value = value.strip().lower()
    return value if value.startswith("0x") else f"0x{value}"


def _bind_address(label: str, key_hex: str, address_var: str, via: str | None) -> str:
    """Return ``key_hex`` once it is bound to the address declared in ``address_var``.

    ``via`` names the env var the key was read through, or is None for a literal.
    A key reached by indirection resolves per host, so it must be declared: without
    the declaration the script would silently register whichever identity the local
    environment happens to hold. Messages carry addresses only, never key material.
    """
    derived, _ = _derive_address_and_public_key(key_hex)
    declared = os.environ.get(address_var, "").strip()
    if not declared:
        if via is not None:
            _die(
                f"{label} is read through {via!r} and resolves to {derived} on this host; "
                f"set {address_var} to the address it must have (the same on every host)"
            )
        return key_hex
    if _normalize_address(declared) != _normalize_address(derived):
        _die(f"{label} resolves to {derived} but {address_var} declares {declared}; refusing to register a different identity")
    return key_hex


def _get_admin_private_key() -> str:
    """Return the admin private key, reading from a referenced env var if needed.

    Bound to ``BRIDGE_ADMIN_ADDRESS`` (required whenever the key comes through an env var name).
    """
    address_var = "BRIDGE_ADMIN_ADDRESS"
    literal = os.environ.get("BRIDGE_ADMIN_PRIVATE_KEY", "").strip()
    if literal:
        return _bind_address("admin", literal.removeprefix("0x"), address_var, None)

    key_file = os.environ.get("BRIDGE_ADMIN_PRIVATE_KEY_FILE", "").strip()
    if key_file:
        contents = _read_key_file(key_file, "admin")
        # A file holds one fixed key — literal class: the address declaration is
        # optional but enforced when present.
        return _bind_address("admin", contents.removeprefix("0x"), address_var, None)

    source_var = os.environ.get("BRIDGE_ADMIN_PRIVATE_KEY_SOURCE", "").strip()
    if source_var:
        if source_var not in os.environ:
            _die(f"admin private key source env var {source_var!r} is not set")
        return _bind_address("admin", os.environ[source_var].strip().removeprefix("0x"), address_var, source_var)

    # Fallbacks for the canonical hub admin (proposer / genesis); still bound to a declared address.
    for fallback in ("PROPOSER_KEY", "GENESIS_PRIVATE_KEY"):
        if os.environ.get(fallback, "").strip():
            return _bind_address("admin", os.environ[fallback].strip().removeprefix("0x"), address_var, fallback)

    _die(
        "no admin private key found. Set BRIDGE_ADMIN_PRIVATE_KEY, "
        "BRIDGE_ADMIN_PRIVATE_KEY_FILE, BRIDGE_ADMIN_PRIVATE_KEY_SOURCE, "
        "PROPOSER_KEY, or GENESIS_PRIVATE_KEY."
    )


def _read_key_file(path_str: str, label: str) -> str:
    """Read a private key from ``path_str``, refusing unsafe files.

    Fails closed: the file must be unreadable by group/other (mode bits
    ``0o077`` clear) and owned by the effective user or root. Messages name
    the path only — never key material.
    """
    path = Path(path_str)
    if path.is_symlink() and path.resolve().parent != path.parent:
        _die(f"{label} key file {path_str!r} is a symlink resolving outside its own directory; refusing")
    try:
        st = path.stat()
    except OSError as exc:
        _die(f"{label} key file {path_str!r} could not be read: {exc.strerror or exc}")
    if st.st_mode & 0o077:
        _die(f"{label} key file {path_str!r} is group/world-readable (mode {oct(st.st_mode & 0o777)}); refusing")
    if st.st_uid not in (os.geteuid(), 0):
        _die(f"{label} key file {path_str!r} is owned by uid {st.st_uid}, not the current user or root; refusing")
    try:
        contents = Path(path_str).read_text().strip()
    except OSError as exc:
        _die(f"{label} key file {path_str!r} could not be read: {exc.strerror or exc}")
    if not contents:
        _die(f"{label} key file {path_str!r} is empty")
    return contents


def _collect_validator_private_keys() -> list[tuple[str, str]]:
    """Collect validator private keys from BRIDGE_VALIDATOR_PRIVATE_KEY(_SOURCE|_FILE)_<N>.

    Validator ``N`` is bound to ``BRIDGE_VALIDATOR_ADDRESS_<N>`` (required whenever its key
    comes through an env var name), so slot ``N`` is the same identity on every host.
    """
    validators: list[tuple[str, str]] = []
    n = 1
    while True:
        source_var = f"BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_{n}"
        literal_var = f"BRIDGE_VALIDATOR_PRIVATE_KEY_{n}"
        file_var = f"BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_{n}"
        address_var = f"BRIDGE_VALIDATOR_ADDRESS_{n}"

        literal = os.environ.get(literal_var, "").strip()
        source = os.environ.get(source_var, "").strip()
        key_file = os.environ.get(file_var, "").strip()

        if not literal and not source and not key_file:
            break

        key: str
        if literal:
            key = _bind_address(f"validator {n}", literal.removeprefix("0x"), address_var, None)
        elif key_file:
            contents = _read_key_file(key_file, f"validator {n}")
            key = _bind_address(f"validator {n}", contents.removeprefix("0x"), address_var, None)
        else:
            if source not in os.environ:
                _die(f"validator {n} private key source env var {source!r} is not set")
            key = _bind_address(f"validator {n}", os.environ[source].strip().removeprefix("0x"), address_var, source)

        validators.append((f"validator-{n}", key))
        n += 1

    if not validators:
        _die(
            "no validator private keys found. Set BRIDGE_VALIDATOR_PRIVATE_KEY_1, "
            "BRIDGE_VALIDATOR_PRIVATE_KEY_FILE_1, or BRIDGE_VALIDATOR_PRIVATE_KEY_SOURCE_1 "
            "(and increment for more)."
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


def _self_sign_data(chain_id: str, address: str, public_key: str) -> dict[str, Any]:
    """The exact field set the handler verifies the validator self-signature over."""
    return {
        "chain_id": chain_id,
        "address": address,
        "public_key": public_key,
        "action": "register",
    }


def _recover_address(data: dict[str, Any], signature_hex: str) -> str:
    """ecrecover the signer of ``data`` (canonical-JSON + keccak) via eth_keys."""
    from eth_keys import keys
    from eth_utils import keccak

    sig = keys.Signature(signature_bytes=bytes.fromhex(signature_hex.removeprefix("0x")))
    return str(sig.recover_public_key_from_msg_hash(keccak(_canonical_json(data))).to_checksum_address())


def _load_validator_blobs(paths: list[str], chain_id: str) -> list[dict[str, str]]:
    """Load pre-signed validator blobs and verify each self-signature.

    A blob carries ``{chain_id, address, public_key, signature}`` — public
    fields only, produced on the key-owning host via ``--emit-blobs``. The
    self-signature must recover to the declared address over the exact
    ``{chain_id, address, public_key, action: register}`` dict, else the
    blob is refused. Blob ``chain_id`` must match ``--chain-id``.
    """
    import json as _json

    out: list[dict[str, str]] = []
    for path in paths:
        try:
            blob = _json.loads(Path(path).read_text())
        except (OSError, RecursionError, ValueError) as exc:
            _die(f"validator blob {path!r} could not be read: {exc}")
        for field in ("chain_id", "address", "public_key", "signature"):
            if not blob.get(field):
                _die(f"validator blob {path!r} is missing {field!r}")
        if blob["chain_id"] != chain_id:
            _die(f"validator blob {path!r} is for chain {blob['chain_id']!r}, not {chain_id!r}")
        try:
            recovered = _recover_address(_self_sign_data(chain_id, blob["address"], blob["public_key"]), blob["signature"])
        except Exception as exc:  # noqa: BLE001 - any recovery failure is fatal: report and die
            _die(f"validator blob {path!r} signature could not be recovered: {exc}")
        if _normalize_address(recovered) != _normalize_address(blob["address"]):
            _die(f"validator blob {path!r} signature recovers to {recovered}, not declared address {blob['address']}")
        out.append(
            {
                "name": Path(path).stem,
                "address": blob["address"],
                "public_key": blob["public_key"],
                "signature": blob["signature"],
            }
        )
    return out


def _probe_node_identity(rpc_url: str) -> tuple[str | None, str | None]:
    """Return ``(chain_id, node_id)`` of the node behind ``rpc_url``, either may be None.

    ``target_chain_id`` in the admin-signed payload binds the node serving the
    request — its OWN chain id, not the chain being registered (Refs #679:
    registering bc-2-island-1 validators on bc-2 nodes needs
    ``target_chain_id=bc-2``). The node's ``/network-info`` answers with the
    authoritative value.
    """
    import httpx

    try:
        with httpx.Client(timeout=5) as client:
            info = client.get(rpc_url.rstrip("/") + "/network-info").json()
    except Exception:  # noqa: BLE001 - optional probe; callers fall back with a warning
        return None, None
    if not isinstance(info, dict):
        return None, None
    chain_id = info.get("chain_id") or None
    node_id = info.get("node_id")
    if node_id in (None, "unknown"):
        node_id = None
    return chain_id, node_id


def _post_registration(rpc_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST the signed payload to the bridge validator registration RPC."""
    import httpx

    url = rpc_url.rstrip("/") + "/bridge/validators/register"
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=payload)
            try:
                return resp.json()
            except ValueError:
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
        help="Chain ID to register validators for (the remote chain — NOT "
        "target_chain_id, which is resolved per destination node).",
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
    parser.add_argument(
        "--emit-blobs",
        metavar="DIR",
        default="",
        help="Write each validator's public self-signature blob to DIR and exit "
        "(run on the key-owning host; keys never leave it).",
    )
    parser.add_argument(
        "--validator-blob",
        action="append",
        default=[],
        metavar="PATH",
        help="Pre-signed validator blob produced by --emit-blobs (repeatable). Skips validator key collection entirely.",
    )

    args = parser.parse_args()

    # Load env files first so all key lookups work.
    for env_path in args.env_file:
        _load_env_file(env_path)

    if not args.rpc_url:
        # Try a comma-separated env var, otherwise default to localhost.
        urls = os.environ.get("BRIDGE_RPC_URLS", "http://127.0.0.1:8202/rpc").split(",")
        args.rpc_url = [u.strip() for u in urls if u.strip()]

    if args.validator_blob:
        # Consume pre-signed blobs: address/public_key/self_signature already
        # produced on the key-owning host — no validator keys needed here.
        identities = _load_validator_blobs(args.validator_blob, args.chain_id)
    else:
        identities = []
        for name, validator_key in _collect_validator_private_keys():
            address, public_key = _derive_address_and_public_key(validator_key)
            identities.append(
                {
                    "name": name,
                    "address": address,
                    "public_key": public_key,
                    "signature": _sign_dict(validator_key, _self_sign_data(args.chain_id, address, public_key)),
                }
            )

    if args.emit_blobs:
        import json as _json

        out_dir = Path(args.emit_blobs)
        out_dir.mkdir(parents=True, exist_ok=True)
        for ident in identities:
            blob = {
                "chain_id": args.chain_id,
                "address": ident["address"],
                "public_key": ident["public_key"],
                "signature": ident["signature"],
            }
            target = out_dir / f"{ident['name']}.json"
            target.write_text(_json.dumps(blob, indent=2) + "\n")
            print(f"wrote {target}: address={ident['address']}")
        return 0

    admin_key = _get_admin_private_key()
    admin_address, _ = _derive_address_and_public_key(admin_key)

    all_ok = True

    print(f"Admin address (derived): {admin_address}")
    print(f"Registering {len(identities)} validator(s) against {len(args.rpc_url)} RPC endpoint(s)")

    for ident in identities:
        name = ident["name"]
        address = ident["address"]
        public_key = ident["public_key"]
        self_signature = ident["signature"]

        if args.dry_run:
            print(f"[DRY-RUN] {name}: address={address}")
            continue

        for rpc_url in args.rpc_url:
            # target_chain_id binds the node SERVING the request — its own
            # chain id, not the chain being registered (Refs #679). Probe the
            # destination so registering a remote island's validators works.
            node_chain, node_id = _probe_node_identity(rpc_url)
            target_chain = node_chain or args.chain_id
            if node_chain is None:
                _warn(
                    f"{rpc_url}: could not probe /network-info for the node's own chain id; "
                    f"falling back to target_chain_id={args.chain_id!r} — this fails unless the "
                    "node runs that chain itself"
                )

            # Build the full payload that the admin will co-sign. Fresh
            # issued_at/nonce per destination: each POST is a separate signed
            # request and nonces are single-use per node.
            payload: dict[str, Any] = {
                "chain_id": args.chain_id,
                "address": address,
                "public_key": public_key,
                "signature": self_signature,
                "epoch": args.epoch,
                "admin_address": admin_address,
                "issued_at": datetime.now(UTC).isoformat(),
                "nonce": secrets.token_hex(16),
                "target_chain_id": target_chain,
            }
            if node_id:
                payload["target_node_id"] = node_id

            # Admin signature covers the payload excluding admin_signature itself.
            payload["admin_signature"] = _sign_dict(admin_key, payload)

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
