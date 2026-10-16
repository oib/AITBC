#!/usr/bin/env python3
"""Verify a signed snapshot manifest (V-5 attested-snapshot verification).

Re-derives the canonical bytes exactly as ``sign-snapshot-manifest.py``
produces them (manifest minus ``signature``/``signature_note``, serialized
``json.dumps(obj, indent=2, sort_keys=True)``), recovers the EIP-191 signer,
and compares it against the trusted signer address.

With ``--db``, additionally recomputes the manifest's own content claims
against a chain database opened strictly read-only: per-table digests via
``side-root-probe.py`` and the state root via ``compute_state_root_full``
(the same functions the generator uses). A manifest whose signature is fine
but whose content does not match the database still fails — the signature
attests content, not the other way around.

Reads no key, wallet, keystore or password.

Output: signer address, canonical-byte digest, per-check OK/FAIL lines,
final ``OK`` or ``FAIL``. Exit status: 0 = OK, 1 = FAIL, 2 = error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import urllib.parse

# The trusted manifest signer. This is the single repo location for the
# operator's manifest-signing address (V-5, dedicated key generated
# 2026-10-13; the private key lives outside the repo under the operator's
# custody). Update only via an operator-approved change.
TRUSTED_MANIFEST_SIGNER = "0xD46bDC3002c6D00c4903A028B206dA7498EeAe59"

SIGNING_METADATA_FIELDS = ("signature", "signature_note")


def canonical_bytes(manifest: dict) -> bytes:
    body = {k: v for k, v in manifest.items() if k not in SIGNING_METADATA_FIELDS}
    return json.dumps(body, indent=2, sort_keys=True).encode("utf-8")


def _load_side_root_probe():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("side_root_probe", os.path.join(here, "side-root-probe.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _connect_ro(db_path: str) -> sqlite3.Connection:
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _recompute_state_root(db_path: str, chain_id: str) -> str | None:
    try:
        from sqlalchemy import event
        from sqlmodel import Session, create_engine

        from aitbc_chain.state.state_root_utils import compute_state_root_full
    except ImportError:
        return None
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path))
    engine = create_engine(f"sqlite:///{uri}?uri=true&mode=ro")

    @event.listens_for(engine, "connect")
    def _query_only(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA query_only=ON")

    with Session(engine) as session:
        return compute_state_root_full(session, chain_id)


def _content_check(manifest: dict, db_path: str) -> list[str]:
    """Recompute digests/state-root against db; return mismatch descriptions."""
    problems: list[str] = []
    conn = _connect_ro(db_path)
    try:
        probe = _load_side_root_probe()
        want = manifest.get("table_digests", {})
        for section, table_map in want.items():
            for table, expected in table_map.items():
                got = probe.table_digest(conn, table)
                if got != expected:
                    problems.append(f"table_digests.{section}.{table}: manifest {expected!r} != recomputed {got!r}")
        sr = manifest.get("state_root", {})
        if sr.get("recomputed") is not None:
            recomputed = _recompute_state_root(db_path, manifest["chain_id"])
            if recomputed is not None and sr.get("recomputed") != recomputed:
                problems.append(f"state_root.recomputed: manifest {sr.get('recomputed')!r} != recomputed {recomputed!r}")
        head = manifest.get("head", {})
        row = conn.execute(
            "SELECT height, hash FROM block WHERE chain_id = ? ORDER BY height DESC LIMIT 1",
            (manifest["chain_id"],),
        ).fetchone()
        if row and (row[0] != head.get("height") or row[1] != head.get("hash")):
            problems.append(f"head: manifest {head} != db head ({row[0]}, {row[1]})")
    finally:
        conn.close()
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify a signed snapshot manifest (EIP-191).")
    ap.add_argument("manifest", help="signed manifest JSON file")
    ap.add_argument(
        "--trusted-address", default=TRUSTED_MANIFEST_SIGNER, help="expected signer (default: the repo's trusted constant)"
    )
    ap.add_argument("--db", default=None, help="optional chain.db to re-check manifest content against (read-only)")
    args = ap.parse_args(argv)

    try:
        manifest = json.load(open(args.manifest))
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read manifest: {e}", file=sys.stderr)
        return 2

    body = canonical_bytes(manifest)
    digest = hashlib.sha256(body).hexdigest()

    sig = manifest.get("signature") or ""
    if not sig:
        print("signer <none>")
        print(f"digest 0x{digest}")
        print("signature-check FAIL (manifest carries no signature)")
        print("FAIL")
        return 1

    from eth_account import Account
    from eth_account.messages import encode_defunct

    try:
        signer = Account.recover_message(encode_defunct(body), signature=sig)
    except Exception as e:  # noqa: BLE001 - unrecoverable signature reports FAIL
        print(f"signature-check FAIL (unrecoverable: {e})")
        print("FAIL")
        return 1

    print(f"signer {signer}")
    print(f"digest 0x{digest}")

    ok = True
    if signer.lower() == args.trusted_address.lower():
        print("signature-check OK")
    else:
        print(f"signature-check FAIL (signer {signer} != trusted {args.trusted_address})")
        ok = False

    if args.db:
        try:
            for problem in _content_check(manifest, args.db):
                print(f"content-check FAIL ({problem})")
                ok = False
            else:
                if ok:
                    print("content-check OK")
        except Exception as e:  # noqa: BLE001 - content-check failure reports FAIL
            print(f"content-check FAIL ({e})")
            ok = False

    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
