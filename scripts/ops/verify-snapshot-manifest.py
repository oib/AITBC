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
from typing import Any

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


def _check_table_digests(problems: list[str], conn: Any, manifest: dict, probe: Any) -> None:
    """Every table the generator digests must be attested, and every attested
    digest must recompute to the same value."""
    digests = manifest.get("table_digests", {})
    for section, tables in (
        ("candidates", probe.CANDIDATE_TABLES),
        ("controls", probe.CONTROL_TABLES),
    ):
        have = digests.get(section, {})
        if not isinstance(have, dict):
            problems.append(f"table_digests.{section}: missing or not an object")
            continue
        for table in tables:
            if table not in have:
                problems.append(f"table_digests.{section}.{table}: missing from manifest")
    for section, table_map in digests.items():
        for table, expected in table_map.items():
            got = probe.table_digest(conn, table)
            if got != expected:
                problems.append(f"table_digests.{section}.{table}: manifest {expected!r} != recomputed {got!r}")


def _check_row_counts(problems: list[str], conn: Any, manifest: dict) -> None:
    """Every manifest-listed table must match, and every db table must be
    listed — an uncounted table is unaudited content."""
    want_counts = manifest.get("row_counts")
    if not isinstance(want_counts, dict) or not want_counts:
        problems.append("row_counts: missing or empty in manifest")
        return
    actual = {
        name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]  # nosec - name from sqlite_master
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    }
    for table, expected in want_counts.items():
        got = actual.get(table)
        if got != expected:
            problems.append(f"row_counts.{table}: manifest {expected!r} != db {got!r}")
    for table in actual:
        if table not in want_counts:
            problems.append(f"row_counts.{table}: present in db but missing from manifest")


def _check_state_root(problems: list[str], manifest: dict, db_path: str, sr: dict) -> None:
    """The manifest's state_root must have been computed, must recompute to the
    same value here, and must not itself attest a mismatch."""
    if sr.get("skipped") or sr.get("recomputed") is None:
        problems.append(
            "state_root: manifest root was skipped/not recomputed (recomputed is null — pass --skip-state-root to waive)"
        )
    else:
        recomputed = _recompute_state_root(db_path, manifest.get("chain_id", ""))
        if recomputed is None:
            problems.append("state_root: cannot recompute here (aitbc_chain unavailable); pass --skip-state-root to waive")
        elif sr.get("recomputed") != recomputed:
            problems.append(f"state_root.recomputed: manifest {sr.get('recomputed')!r} != recomputed {recomputed!r}")
    if not sr.get("match"):
        problems.append("state_root.match: manifest itself attests recorded != recomputed")


def _check_head(problems: list[str], conn: Any, manifest: dict, sr: dict) -> None:
    """The manifest's head must be the db's head row, and the recorded state
    root must be that row's state_root."""
    row = conn.execute(
        "SELECT height, hash, state_root FROM block WHERE chain_id = ? ORDER BY height DESC LIMIT 1",
        (manifest.get("chain_id"),),
    ).fetchone()
    if row is None:
        problems.append(f"head: chain {manifest.get('chain_id')!r} has no block row in db")
        return
    head = manifest.get("head", {})
    if row[0] != head.get("height") or row[1] != head.get("hash"):
        problems.append(f"head: manifest {head} != db head ({row[0]}, {row[1]})")
    if sr.get("recorded") != row[2]:
        problems.append(f"state_root.recorded: manifest {sr.get('recorded')!r} != db head state_root {row[2]!r}")


def _content_check(manifest: dict, db_path: str, *, skip_state_root: bool = False) -> list[str]:
    """Recompute digests/row-counts/state-root against db; return mismatch descriptions.

    Everything the manifest attests is checked, and everything the generator
    is expected to attest must be present: an absent chain, a missing head
    row, a row_counts mismatch, a skipped/unrecomputable/mismatched state
    root, a recorded root that differs from the db head's, or a missing
    candidate/control table is a problem — not a silent pass.
    """
    problems: list[str] = []
    conn = _connect_ro(db_path)
    try:
        probe = _load_side_root_probe()
        sr = manifest.get("state_root", {})
        _check_table_digests(problems, conn, manifest, probe)
        _check_row_counts(problems, conn, manifest)
        if not skip_state_root:
            _check_state_root(problems, manifest, db_path, sr)
        _check_head(problems, conn, manifest, sr)
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
    ap.add_argument(
        "--skip-state-root",
        action="store_true",
        help="waive the state-root recompute checks (skipped/missing/unrecomputable root); printed loudly",
    )
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
        if args.skip_state_root:
            print("content-check NOTE (--skip-state-root: state-root recompute checks waived)")
        try:
            problems = _content_check(manifest, args.db, skip_state_root=args.skip_state_root)
            for problem in problems:
                print(f"content-check FAIL ({problem})")
            if not problems:
                print("content-check OK")
            else:
                ok = False
        except Exception as e:  # noqa: BLE001 - content-check failure reports FAIL
            print(f"content-check FAIL ({e})")
            ok = False

    print("OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
