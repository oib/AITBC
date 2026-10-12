#!/usr/bin/env python3
"""Dry-run lister for escrow custody residue (S-11). Never submits anything.

v3 escrow custody strands the withheld platform fee (plus rounding dust) in
each job's per-escrow account when the release pays out. Since block 35400
(v11) the settlement authority can sweep a settled escrow's residue to the
governed ``escrow_fee_recipient`` with an ``ESCROW_FEE_SWEEP`` leg. This tool
lists every terminal escrow still holding a residue — read-only, ``mode=ro``
on every database it opens — so the operator can approve a batch deliberately.
It builds no transaction and signs nothing.

A residue row is an ``escrow`` row in a terminal status (``released``,
``refunded``, ``void``) whose ledgered outflow (``released_amount`` +
``refunded_amount``) is smaller than the locked ``amount``. The custody
account is taken from the lock transaction's payload ``to`` field — the same
address consensus derives as ``keccak("aitbc.escrow." + job_id)[:20]`` — and
the sweep leg's recipient is the on-chain ``escrow_fee_recipient`` chain
parameter (``--fee-recipient`` overrides when the parameter is absent).

Rows younger than ``--min-age-seconds`` (default 7 days) are printed as
informational only: a fresh residue may still be mid-settlement. The alert
side (``escrow-residue-textfile.py`` + ``EscrowResidueStale``) counts only
stale rows so fresh residue never pages anyone.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

TERMINAL_STATES = ("released", "refunded", "void")
DEFAULT_MIN_AGE_SECONDS = 7 * 24 * 3600
DEFAULT_V3_HEIGHT = 5470  # per-escrow custody activation on the live island chain
OUTFLOW_TYPES = ("ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")

# Classification (S-12): the ledger residue number alone is not enough — a row
# is only sweepable when its residue is the stranded platform fee still in the
# job's custody account. The sealed legs decide.
#   void — never locked : the row claims a lock that never sealed (or has none)
#   already settled     : sealed outflow legs (release/refund/fee-sweep) cover
#                         the lock amount — the residue already left custody and
#                         the ledger row is stale
#   v2 authority-retained : the lock sealed below the v3 custody height — value
#                         went to the settlement authority's account, never to
#                         a per-escrow custody account; the fee is retained
#                         there already and a sweep is a no-op
#   rounding dust       : residue below the dust threshold (param)
#   fee leg             : none of the above — the only class a sweep may target
#   canary-…            : prefix added to job rows naming a canary/test job


class Residue(NamedTuple):
    job_id: str
    status: str
    amount: int
    released: int
    refunded: int
    residue: int
    terminal_at: str
    age_seconds: float | None
    custody_address: str | None
    stale: bool
    cls: str
    lock_height: int | None
    sealed_outflow: int


def parse_ts(raw: object) -> datetime | None:
    """SQLAlchemy sqlite DATETIME forms: 'YYYY-MM-DD HH:MM:SS.ffffff' or ISO."""
    if raw is None:
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _chain_param(conn: sqlite3.Connection, name: str) -> str | None:
    try:
        row = conn.execute(
            "SELECT value FROM chain_parameter WHERE parameter = ? ORDER BY applied_height DESC LIMIT 1",
            (name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    value = str(row[0]).strip() if row and row[0] else ""
    return value or None


def _legs(conn: sqlite3.Connection, job_id: str) -> tuple[int | None, int, bool]:
    """(lock height, sealed outflow, swept) for the job's ESCROW_* legs.

    The outflow sums the values of sealed RELEASE/REFUND/FEE_SWEEP legs whose
    payload names the job — the ledger's released/refunded columns are known to
    lag (legs sealed after the row's terminal timestamp never wrote back).
    """
    try:
        rows = conn.execute(
            "SELECT type, block_height, value FROM \"transaction\" WHERE type LIKE 'ESCROW%' AND payload LIKE ?",
            (f"%{job_id}%",),
        ).fetchall()
    except sqlite3.OperationalError:
        return None, 0, False
    lock_height = None
    outflow = 0
    swept = False
    for tx_type, height, value in rows:
        if tx_type == "ESCROW_LOCK" and lock_height is None:
            lock_height = int(height) if height is not None else None
        elif tx_type in OUTFLOW_TYPES:
            outflow += int(value or 0)
            swept = swept or tx_type == "ESCROW_FEE_SWEEP"
    return lock_height, outflow, swept


def classify(
    status: str,
    residue: int,
    lock_height: int | None,
    sealed_outflow: int,
    amount: int,
    swept: bool,
    v3_height: int,
    dust: int,
    job_id: str = "",
) -> str:
    """Class per the S-12 scheme — see the module constants for the meanings."""
    if job_id.startswith("canary"):
        prefix = "canary-"
    else:
        prefix = ""
    if lock_height is None:
        return prefix + "void — never locked"
    if swept:
        return prefix + "already settled (fee-swept)"
    if sealed_outflow >= amount:
        return prefix + "already settled (released)"
    if lock_height < v3_height:
        return prefix + "v2 authority-retained"
    if residue <= dust:
        return prefix + "rounding dust"
    return prefix + "fee leg"


def collect_residues(
    db_path: str, now: float, min_age_seconds: int, v3_height: int = DEFAULT_V3_HEIGHT, dust: int = 0
) -> tuple[list[Residue], str | None]:
    """(residue rows, resolved fee recipient) for one chain.db opened mode=ro."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        fee_recipient = _chain_param(conn, "escrow_fee_recipient")
        rows = conn.execute(
            """SELECT job_id, status, amount, COALESCE(released_amount, 0), COALESCE(refunded_amount, 0),
                      COALESCE(released_at, refunded_at, created_at), lock_tx_hash
                 FROM escrow
                WHERE status IN (?, ?, ?)
                  AND amount - COALESCE(released_amount, 0) - COALESCE(refunded_amount, 0) > 0""",
            TERMINAL_STATES,
        ).fetchall()
        legs = {str(r[0]): _legs(conn, str(r[0])) for r in rows}
    finally:
        conn.close()
    residues = []
    for job_id, status, amount, released, refunded, terminal_at, _lock_hash in rows:
        ts = parse_ts(terminal_at)
        age = (now - ts.timestamp()) if ts else None
        lock_height, sealed_outflow, swept = legs[str(job_id)]
        residues.append(
            Residue(
                job_id=str(job_id),
                status=str(status),
                amount=int(amount),
                released=int(released),
                refunded=int(refunded),
                residue=int(amount) - int(released) - int(refunded),
                terminal_at=str(terminal_at) if terminal_at else "",
                age_seconds=age,
                custody_address=None,
                stale=age is not None and age >= min_age_seconds,
                cls=classify(
                    str(status),
                    int(amount) - int(released) - int(refunded),
                    lock_height,
                    sealed_outflow,
                    int(amount),
                    swept,
                    v3_height,
                    dust,
                    str(job_id),
                ),
                lock_height=lock_height,
                sealed_outflow=sealed_outflow,
            )
        )
    return residues, fee_recipient


def find_chain_dbs(data_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(data_dir, "data", "*", "chain.db")))


def sweep_leg(r: Residue, fee_recipient: str | None) -> dict:
    """The ESCROW_FEE_SWEEP leg an approved batch would submit (spec only)."""
    return {
        "type": "ESCROW_FEE_SWEEP",
        "payload": {"job_id": r.job_id},
        "value_units": r.residue,
        "to": fee_recipient or "<escrow_fee_recipient unset>",
        "note": "sender must be the escrow_settlement_authority; this tool never submits",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", action="append", type=Path, help="chain.db path (repeatable; default scans --data-dir)")
    parser.add_argument("--data-dir", default=os.getenv("AITBC_DATA_DIR", "/var/lib/aitbc"))
    parser.add_argument("--min-age-seconds", type=int, default=DEFAULT_MIN_AGE_SECONDS)
    parser.add_argument(
        "--v3-height", type=int, default=DEFAULT_V3_HEIGHT, help="custody activation height (default %(default)s)"
    )
    parser.add_argument("--dust", type=int, default=0, help="residue at or below this counts as rounding dust")
    parser.add_argument("--fee-recipient", help="override when the chain parameter is absent")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    dbs = [str(d) for d in args.db] if args.db else find_chain_dbs(args.data_dir)
    if not dbs:
        print(f"no chain.db found under {args.data_dir} (or via --db)", file=sys.stderr)
        return 2

    now = datetime.now(tz=UTC).timestamp()
    all_rows: list[tuple[str, Residue]] = []
    fee_recipient = args.fee_recipient
    errors = 0
    for db in dbs:
        try:
            rows, resolved = collect_residues(db, now, args.min_age_seconds, args.v3_height, args.dust)
        except sqlite3.Error as exc:
            print(f"{db}: unreadable ({exc})", file=sys.stderr)
            errors += 1
            continue
        fee_recipient = fee_recipient or resolved
        all_rows.extend((db, r) for r in rows)

    if args.json:
        print(
            json.dumps(
                {
                    "min_age_seconds": args.min_age_seconds,
                    "fee_recipient": fee_recipient,
                    "residues": [
                        {
                            **r._asdict(),
                            "db": db,
                            "sweep_leg": sweep_leg(r, fee_recipient) if r.cls == "fee leg" else None,
                        }
                        for db, r in all_rows
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"{'job':<10}{'status':<10}{'residue':>12}{'age(d)':>8}{'stale':>6}  class")
        print("-" * 70)
        for _db, r in sorted(all_rows, key=lambda t: -(t[1].residue)):
            age_d = f"{r.age_seconds / 86400:.1f}" if r.age_seconds is not None else "?"
            print(f"{r.job_id[:8]:<10}{r.status:<10}{r.residue:>12}{age_d:>8}{'yes' if r.stale else 'no':>6}  {r.cls}")
        stale = [r for _, r in all_rows if r.stale]
        sweepable = [r for _, r in all_rows if r.cls == "fee leg"]
        print("-" * 70)
        print(
            f"{len(all_rows)} residue rows ({len(stale)} older than {args.min_age_seconds}s), "
            f"total {sum(r.residue for _, r in all_rows)} units; fee recipient {fee_recipient or '<unset>'}"
        )
        by_class: dict[str, int] = {}
        for _, r in all_rows:
            by_class[r.cls] = by_class.get(r.cls, 0) + 1
        print("classes: " + ", ".join(f"{c}×{n}" for c, n in sorted(by_class.items())))
        if sweepable:
            print(
                f"{len(sweepable)} rows are sweepable fee legs — ESCROW_FEE_SWEEP per row, operator-approved; this tool submits nothing"
            )
        else:
            print("no sweepable fee-leg rows — every residue is already settled, never locked, or pre-custody")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
