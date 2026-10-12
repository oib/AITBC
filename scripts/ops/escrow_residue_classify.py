"""Shared escrow-residue row classification (S-12 scheme, S-15 extraction).

Used by ``scripts/ops/escrow_residue_dryrun.py`` (operator dry-run lister) and
``scripts/monitoring/escrow-residue-textfile.py`` (Prometheus textfile
exporter) so the two can never disagree on what counts as sweepable.

A residue row is an ``escrow`` row in a terminal status whose ledgered outflow
(``released_amount`` + ``refunded_amount``) is smaller than the locked
``amount``. The ledger number alone is misleading — the sealed ``ESCROW_*``
legs decide the class:

    void — never locked         the row claims a lock that never sealed (or has none)
    already settled (fee-swept) an ESCROW_FEE_SWEEP already ran for the job
    already settled (released)  sealed outflow legs cover the lock amount — the
                                residue already left custody; the row is stale
    v2 authority-retained       the lock sealed below the v3 custody height — value
                                went to the settlement authority's account, never
                                to a per-escrow custody account; a sweep is a no-op
    rounding dust               residue at or below the dust threshold
    fee leg                     none of the above — the only class a sweep may target

Stdlib only; both callers importlib-load or ``sys.path``-import this module
from the scripts tree, so it must not depend on the repo's packages.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

TERMINAL_STATES = ("released", "refunded", "void")
OUTFLOW_TYPES = ("ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")
DEFAULT_V3_HEIGHT = 5470  # per-escrow custody activation on the live island chain

FEE_LEG = "fee leg"
INFORMATIONAL_CLASSES = (
    "void — never locked",
    "already settled (released)",
    "already settled (fee-swept)",
    "v2 authority-retained",
    "rounding dust",
)


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


def legs(conn: sqlite3.Connection, job_id: str) -> tuple[int | None, int, bool]:
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
    residue: int, amount: int, lock_height: int | None, sealed_outflow: int, swept: bool, v3_height: int, dust: int
) -> str:
    """S-12 class — only ``fee leg`` is sweepable/alertable."""
    if lock_height is None:
        return "void — never locked"
    if swept:
        return "already settled (fee-swept)"
    if sealed_outflow >= amount:
        return "already settled (released)"
    if lock_height < v3_height:
        return "v2 authority-retained"
    if residue <= dust:
        return "rounding dust"
    return FEE_LEG
