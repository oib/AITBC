#!/usr/bin/env python3
"""Remove the retired test and canary GPU rows from a chain.db, idempotently.

On 2 Oct 2026 ten ``gpu_registration`` rows and the two ``gpu_allocation`` rows
on ``canary9-gpu-001`` were deleted by SQL on every fleet node. Eight of those
registrations (and both allocations) were created by sealed ``GPU_REGISTER`` /
``GPU_ALLOCATE`` transactions, so anything that re-applies those blocks writes
the rows again: a chain backup older than the cleanup, or a checkpoint replay
(``scripts/ops/replay-chain.py``). Both tables are consensus-class, so the
restored database then drifts from the fleet's table digests.

This script is the repair step for such a database. It deletes the retired
registrations and the allocations that reference them, and prints what it did.
Running it on a database that is already clean changes nothing.

It is meant for a restored or replayed database while its node is stopped.
Live nodes are already clean; do not use it to tidy a running node's registry
(the sealed way to retire a GPU is ``GPU_DEREGISTER``, once v10 is live).

Usage:

    # What would go (read-only, the default):
    python scripts/ops/gpu-registry-sweep.py --chain-id ait-hub.aitbc.bubuit.net \
        --db /var/lib/aitbc/data/ait-hub.aitbc.bubuit.net/chain.db

    # Exit status 3 when retired rows are present, 0 when clean (no change either way):
    python scripts/ops/gpu-registry-sweep.py --chain-id ... --db ... --check

    # Back up the database, then delete in one transaction:
    python scripts/ops/gpu-registry-sweep.py --chain-id ... --db ... --apply

After a sweep, compare the table digests with the fleet
(``scripts/monitoring/fleet-config-check.sh`` runs the digest probe); the two
tables must read the same as on the other hosts.

Rows are matched on ``gpu_id`` and on ``chain_id`` equal to ``--chain-id`` or
empty: two of the retired registrations (``test-rtx4060ti``, ``node2-rtx4060ti``)
were never sealed and carry an empty ``chain_id``.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# gpu_id values removed on 2 Oct 2026. The first eight were created by sealed
# GPU_REGISTER transactions (heights 1647 to 29688); the last two were never sealed.
RETIRED_GPU_IDS: tuple[str, ...] = (
    "canary-gpu-001",
    "canary-gpu-cli-001",
    "canary9-gpu-001",
    "canary9-gpu-v9r2-001",
    "gpu-live-05",
    "gpu-live-06",
    "gpu-live-07",
    "gpu-live-08",
    "test-rtx4060ti",
    "node2-rtx4060ti",
)

DEFAULT_BACKUP_DIR = "/var/backups/aitbc"
EXIT_RETIRED_ROWS_PRESENT = 3


def _placeholders(n: int) -> str:
    return ", ".join("?" for _ in range(n))


def find_rows(conn: sqlite3.Connection, chain_id: str, gpu_ids: tuple[str, ...]) -> dict[str, list[tuple[Any, ...]]]:
    """The registrations and allocations the sweep would delete."""
    marks = _placeholders(len(gpu_ids))
    params = (*gpu_ids, chain_id)
    registrations = conn.execute(
        f"SELECT gpu_id, chain_id, status, registered_by FROM gpu_registration "  # nosec B608 - placeholders only
        f"WHERE gpu_id IN ({marks}) AND (chain_id = ? OR chain_id = '') ORDER BY gpu_id",
        params,
    ).fetchall()
    allocations = conn.execute(
        f"SELECT allocation_id, gpu_id, chain_id, status FROM gpu_allocation "  # nosec B608 - placeholders only
        f"WHERE gpu_id IN ({marks}) AND (chain_id = ? OR chain_id = '') ORDER BY gpu_id, allocation_id",
        params,
    ).fetchall()
    return {"registrations": registrations, "allocations": allocations}


def _has_tables(conn: sqlite3.Connection) -> bool:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return {"gpu_registration", "gpu_allocation"} <= names


def backup_database(db_path: Path, backup_dir: Path) -> Path:
    """Consistent copy of ``db_path`` (sqlite backup API), mode 600, integrity-checked."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{db_path.parent.name}-chain-before-gpu-sweep.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.chmod(target, 0o600)
    check = sqlite3.connect(str(target))
    try:
        verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if verdict != "ok":
        raise RuntimeError(f"backup {target} failed its integrity check: {verdict}")
    return target


def sweep(
    db_path: Path,
    chain_id: str,
    gpu_ids: tuple[str, ...] = RETIRED_GPU_IDS,
    *,
    apply: bool = False,
    backup_dir: Path | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Report, and with ``apply`` delete, the retired rows. Returns what was found and removed.

    ``backup=False`` skips the pre-delete copy; only for a scratch database nobody needs back."""
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        if not _has_tables(conn):
            raise RuntimeError(f"{db_path} has no gpu_registration / gpu_allocation table")
        found = find_rows(conn, chain_id, gpu_ids)
        result: dict[str, Any] = {
            "found": found,
            "removed": {"registrations": 0, "allocations": 0},
            "backup": None,
        }
        if not apply or not (found["registrations"] or found["allocations"]):
            return result
        conn.close()
        if backup:
            result["backup"] = backup_database(db_path, backup_dir or Path(DEFAULT_BACKUP_DIR))
        conn = sqlite3.connect(str(db_path), timeout=30)
        marks = _placeholders(len(gpu_ids))
        params = (*gpu_ids, chain_id)
        # Allocations first: they reference the registrations by gpu_id.
        conn.execute("BEGIN IMMEDIATE")
        try:
            allocs = conn.execute(
                f"DELETE FROM gpu_allocation WHERE gpu_id IN ({marks}) AND (chain_id = ? OR chain_id = '')",  # nosec B608
                params,
            ).rowcount
            regs = conn.execute(
                f"DELETE FROM gpu_registration WHERE gpu_id IN ({marks}) AND (chain_id = ? OR chain_id = '')",  # nosec B608
                params,
            ).rowcount
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        result["removed"] = {"registrations": regs, "allocations": allocs}
        return result
    finally:
        conn.close()


def _counts(db_path: Path, chain_id: str) -> tuple[int, int]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        regs = conn.execute("SELECT count(*) FROM gpu_registration WHERE chain_id IN (?, '')", (chain_id,)).fetchone()[0]
        allocs = conn.execute("SELECT count(*) FROM gpu_allocation WHERE chain_id IN (?, '')", (chain_id,)).fetchone()[0]
    finally:
        conn.close()
    return regs, allocs


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--chain-id", default=os.getenv("CHAIN_ID", ""), help="Chain ID (default: $CHAIN_ID)")
    parser.add_argument("--db", help="chain.db to sweep (default: /var/lib/aitbc/data/<chain-id>/chain.db)")
    parser.add_argument("--apply", action="store_true", help="back up the database, then delete the retired rows")
    parser.add_argument(
        "--check", action="store_true", help=f"change nothing; exit {EXIT_RETIRED_ROWS_PRESENT} if retired rows are present"
    )
    parser.add_argument(
        "--backup-dir", default=DEFAULT_BACKUP_DIR, help=f"where --apply writes its backup (default {DEFAULT_BACKUP_DIR})"
    )
    parser.add_argument(
        "--extra-id", action="append", default=[], metavar="GPU_ID", help="also sweep this gpu_id (repeatable)"
    )
    args = parser.parse_args(argv)
    if not args.chain_id:
        parser.error("--chain-id or CHAIN_ID required")
    if args.apply and args.check:
        parser.error("--apply and --check are mutually exclusive")
    if not args.db:
        args.db = f"/var/lib/aitbc/data/{args.chain_id}/chain.db"
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"FATAL: {db_path} not found", file=sys.stderr)
        return 2
    gpu_ids = (*RETIRED_GPU_IDS, *args.extra_id)
    try:
        result = sweep(db_path, args.chain_id, gpu_ids, apply=args.apply and not args.check, backup_dir=Path(args.backup_dir))
    except (RuntimeError, sqlite3.Error) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    found = result["found"]
    for row in found["registrations"]:
        print(
            f"gpu_registration  gpu_id={row[0]} chain_id={row[1] or '(empty)'} status={row[2]} registered_by={str(row[3])[:10]}"
        )
    for row in found["allocations"]:
        print(f"gpu_allocation    allocation_id={row[0]} gpu_id={row[1]} chain_id={row[2] or '(empty)'} status={row[3]}")
    n_regs, n_allocs = len(found["registrations"]), len(found["allocations"])
    if not (n_regs or n_allocs):
        print("clean: no retired GPU rows present")
        return 0
    if not args.apply:
        print(
            f"{n_regs} registrations and {n_allocs} allocations are retired rows; nothing changed (add --apply to remove them)"
        )
        return EXIT_RETIRED_ROWS_PRESENT if args.check else 0

    removed = result["removed"]
    print(f"backup: {result['backup']}")
    print(f"removed {removed['registrations']} registrations and {removed['allocations']} allocations")
    regs, allocs = _counts(db_path, args.chain_id)
    print(f"now: gpu_registration {regs} rows, gpu_allocation {allocs} rows; compare the table digests with the fleet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
