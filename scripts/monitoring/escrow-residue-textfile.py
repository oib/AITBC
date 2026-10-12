#!/usr/bin/env python3
"""Export stale escrow-custody-residue counts as a node_exporter textfile.

S-11/S-13 detection: v3 escrow custody strands the withheld platform fee in
each job's per-escrow account at release time, and nothing noticed. Since
block 35400 (v11) the settlement authority can sweep the residue to the
governed ``escrow_fee_recipient`` with an ``ESCROW_FEE_SWEEP`` leg — but sweeps
are operator-approved batches, so between batches the residue sits. This
exporter keeps it visible.

S-12 changed what "counts": the ledger residue number alone is misleading —
most rows are already settled on-chain, never locked, or pre-custody (the fee
already sits in the settlement authority's balance). Only a row classed
``fee leg`` is genuinely sweepable, so the alert metric counts just those.
The other classes stay visible on an informational gauge with **no alert
attached**: they are ledger staleness an operator may want to repair, not
money waiting to move.

Classes (same rules as ``scripts/ops/escrow_residue_dryrun.py``):
    void — never locked        row claims a lock that never sealed
    already settled (released) sealed outflow legs cover the lock amount
    already settled (fee-swept) an ESCROW_FEE_SWEEP already ran
    v2 authority-retained      lock sealed below the v3 custody height
    rounding dust              residue at or below the dust threshold
    fee leg                    none of the above — the only alertable class
A ``canary-`` prefix on a job_id marks test jobs (still counted under their
underlying class on the informational gauge; a canary fee leg does alert —
it is real residue).

Reads every chain.db found under ``AITBC_DATA_DIR`` (or the explicit
``AITBC_CHAIN_DB``) read-only — escrow rows are per-node bookkeeping sharing
the consensus chain database, the same model as escrow-settlements-textfile.

Writes, atomically, to ``<TEXTFILE_DIR>/aitbc_escrow_residue.prom``:

    aitbc_escrow_residue_accounts                    stale FEE-LEG rows only (alerted)
    aitbc_escrow_residue_account{job_id=...}         1 per stale fee-leg row
    aitbc_escrow_residue_oldest_seconds              age of the oldest stale fee leg
    aitbc_escrow_residue_stale_ledger_rows{class=..} informational, no alert
    aitbc_escrow_residue_scrape_success{db=...}      1 when the DB read worked
    aitbc_escrow_residue_scrape_timestamp_seconds    when this run finished

A DB that cannot be opened or lacks the escrow table reads as failure, not
"all clear". Run by a systemd timer alongside the other escrow exporters;
stdlib only.

Environment:
    AITBC_CHAIN_DB                          explicit chain.db path (else scan below)
    AITBC_DATA_DIR                          default /var/lib/aitbc; scanned for data/*/chain.db
    AITBC_ESCROW_RESIDUE_MAX_AGE_SECONDS    default 604800 (7d)
    AITBC_ESCROW_RESIDUE_V3_HEIGHT          default 5470 (custody activation)
    AITBC_ESCROW_RESIDUE_DUST               default 0 (residue <= this = rounding dust)
    AITBC_TEXTFILE_DIR                      default /var/lib/prometheus/node-exporter
"""

from __future__ import annotations

import glob
import os
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from typing import NamedTuple

OUTPUT_NAME = "aitbc_escrow_residue.prom"
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600
DEFAULT_V3_HEIGHT = 5470  # per-escrow custody activation on the live island chain
TERMINAL_STATES = ("released", "refunded", "void")
OUTFLOW_TYPES = ("ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")
FEE_LEG = "fee leg"
INFORMATIONAL_CLASSES = (
    "void — never locked",
    "already settled (released)",
    "already settled (fee-swept)",
    "v2 authority-retained",
    "rounding dust",
)


# NamedTuple, not @dataclass: the test suite importlib-loads this script without
# registering it in sys.modules, and dataclass field resolution requires the
# module entry under Python 3.13.
class ResidueRow(NamedTuple):
    job_id: str
    residue: int
    age_seconds: float
    cls: str


def find_chain_dbs(data_dir: str) -> list[str]:
    """Every ``data/*/chain.db`` under the data dir, sorted for determinism."""
    return sorted(glob.glob(os.path.join(data_dir, "data", "*", "chain.db")))


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


def _legs(conn: sqlite3.Connection, job_id: str) -> tuple[int | None, int, bool]:
    """(lock height, sealed outflow, swept) for the job's ESCROW_* legs."""
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
    """S-12 class — only ``fee leg`` is alertable."""
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


def stale_residues(
    conn: sqlite3.Connection, now: float, max_age_seconds: float, v3_height: int, dust: int
) -> list[ResidueRow]:
    rows = conn.execute(
        """SELECT job_id, amount,
                  amount - COALESCE(released_amount, 0) - COALESCE(refunded_amount, 0) AS residue,
                  COALESCE(released_at, refunded_at, created_at) AS terminal_at
             FROM escrow
            WHERE status IN (?, ?, ?)
              AND residue > 0""",
        TERMINAL_STATES,
    ).fetchall()
    out = []
    for job_id, amount, residue, terminal_at in rows:
        ts = parse_ts(terminal_at)
        if ts is None:
            continue  # unparseable timestamp: not stale-countable, not hidden
        age = now - ts.timestamp()
        if age < max_age_seconds:
            continue
        lock_height, sealed_outflow, swept = _legs(conn, str(job_id))
        out.append(
            ResidueRow(
                job_id=str(job_id),
                residue=int(residue),
                age_seconds=age,
                cls=classify(int(residue), int(amount), lock_height, sealed_outflow, swept, v3_height, dust),
            )
        )
    return out


def read_db(path: str, now: float, max_age_seconds: float, v3_height: int, dust: int) -> list[ResidueRow] | None:
    """None on failure — a broken check must not mask the disease it watches."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return stale_residues(conn, now, max_age_seconds, v3_height, dust)
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render(results: dict[str, list[ResidueRow] | None], now: float) -> str:
    """results maps db path → classified residue rows, or None when the read failed."""
    lines = [
        "# HELP aitbc_escrow_residue_accounts Stale escrow residue rows of class fee leg (sweepable).",
        "# TYPE aitbc_escrow_residue_accounts gauge",
        "# HELP aitbc_escrow_residue_account One stale fee-leg residue row.",
        "# TYPE aitbc_escrow_residue_account gauge",
        "# HELP aitbc_escrow_residue_oldest_seconds Age of the oldest stale fee-leg row.",
        "# TYPE aitbc_escrow_residue_oldest_seconds gauge",
        "# HELP aitbc_escrow_residue_stale_ledger_rows Stale residue rows by class (informational; no alert).",
        "# TYPE aitbc_escrow_residue_stale_ledger_rows gauge",
        "# HELP aitbc_escrow_residue_scrape_success 1 when the chain.db read worked.",
        "# TYPE aitbc_escrow_residue_scrape_success gauge",
        "# HELP aitbc_escrow_residue_scrape_timestamp_seconds Unix time of this scrape.",
        "# TYPE aitbc_escrow_residue_scrape_timestamp_seconds gauge",
    ]
    fee_legs = 0
    oldest = 0.0
    by_class: dict[str, int] = {}
    for db, rows in sorted(results.items()):
        ok = rows is not None
        lines.append(f'aitbc_escrow_residue_scrape_success{{db="{_label(db)}"}} {1 if ok else 0}')
        if not ok:
            continue
        for r in rows:
            if r.cls == FEE_LEG:
                fee_legs += 1
                oldest = max(oldest, r.age_seconds)
                lines.append(f'aitbc_escrow_residue_account{{db="{_label(db)}",job_id="{_label(r.job_id)}"}} 1')
            else:
                cls = r.cls.removeprefix("canary-")
                by_class[cls] = by_class.get(cls, 0) + 1
    for cls in INFORMATIONAL_CLASSES:
        lines.append(f'aitbc_escrow_residue_stale_ledger_rows{{class="{_label(cls)}"}} {by_class.get(cls, 0)}')
    lines.append(f"aitbc_escrow_residue_accounts {fee_legs}")
    lines.append(f"aitbc_escrow_residue_oldest_seconds {int(oldest)}")
    lines.append(f"aitbc_escrow_residue_scrape_timestamp_seconds {int(now)}")
    return "\n".join(lines) + "\n"


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_escrow_residue.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.rename(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def resolve_dbs() -> list[str]:
    explicit = os.getenv("AITBC_CHAIN_DB", "").strip()
    if explicit:
        return [explicit]
    return find_chain_dbs(os.getenv("AITBC_DATA_DIR", "/var/lib/aitbc"))


def main() -> int:
    directory = os.getenv("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    max_age = float(os.getenv("AITBC_ESCROW_RESIDUE_MAX_AGE_SECONDS", str(DEFAULT_MAX_AGE_SECONDS)))
    v3_height = int(os.getenv("AITBC_ESCROW_RESIDUE_V3_HEIGHT", str(DEFAULT_V3_HEIGHT)))
    dust = int(os.getenv("AITBC_ESCROW_RESIDUE_DUST", "0"))
    now = time.time()
    dbs = resolve_dbs()
    results: dict[str, list[ResidueRow] | None] = {}
    rc = 0
    for db in dbs or ["<none>"]:
        if db == "<none>":
            results[db] = None
            rc = 1
            continue
        rows = read_db(db, now, max_age, v3_height, dust)
        results[db] = rows
        if rows is None:
            rc = 1
    write_atomic(directory, render(results, now))
    return rc


if __name__ == "__main__":
    sys.exit(main())
