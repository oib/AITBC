#!/usr/bin/env python3
"""Export stale escrow-custody-residue counts as a node_exporter textfile.

S-11 detection: v3 escrow custody strands the withheld platform fee in each
job's per-escrow account at release time, and nothing noticed. Since block
35400 (v11) the settlement authority can sweep the residue to the governed
``escrow_fee_recipient`` with an ``ESCROW_FEE_SWEEP`` leg — but sweeps are
operator-approved batches, so between batches the residue sits. This exporter
keeps it visible: count terminal escrows whose residue is older than
``AITBC_ESCROW_RESIDUE_MAX_AGE_SECONDS`` (default 7 days) and let
``EscrowResidueStale`` warn when any persist. Rows younger than the threshold
are mid-settlement noise and do not count.

A residue row is an ``escrow`` row in a terminal status (``released``,
``refunded``, ``void``) with ``amount > released_amount + refunded_amount``.
Reads every chain.db found under ``AITBC_DATA_DIR`` (or the explicit
``AITBC_CHAIN_DB``) read-only — escrow rows are per-node bookkeeping sharing
the consensus chain database, the same model as escrow-settlements-textfile.

Writes, atomically, to ``<TEXTFILE_DIR>/aitbc_escrow_residue.prom``:

    aitbc_escrow_residue_accounts                    terminal escrows holding stale residue
    aitbc_escrow_residue_account{job_id=...}         1 per stale residue row
    aitbc_escrow_residue_oldest_seconds              age of the oldest stale residue
    aitbc_escrow_residue_scrape_success{db=...}      1 when the DB read worked
    aitbc_escrow_residue_scrape_timestamp_seconds    when this run finished

A DB that cannot be opened or lacks the escrow table reads as failure, not
"all clear". Run by a systemd timer alongside the other escrow exporters;
stdlib only.

Environment:
    AITBC_CHAIN_DB                          explicit chain.db path (else scan below)
    AITBC_DATA_DIR                          default /var/lib/aitbc; scanned for data/*/chain.db
    AITBC_ESCROW_RESIDUE_MAX_AGE_SECONDS    default 604800 (7d)
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
TERMINAL_STATES = ("released", "refunded", "void")


# NamedTuple, not @dataclass: the test suite importlib-loads this script without
# registering it in sys.modules, and dataclass field resolution requires the
# module entry under Python 3.13.
class ResidueRow(NamedTuple):
    job_id: str
    residue: int
    age_seconds: float


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


def stale_residues(conn: sqlite3.Connection, now: float, max_age_seconds: float) -> list[ResidueRow]:
    rows = conn.execute(
        """SELECT job_id,
                  amount - COALESCE(released_amount, 0) - COALESCE(refunded_amount, 0) AS residue,
                  COALESCE(released_at, refunded_at, created_at) AS terminal_at
             FROM escrow
            WHERE status IN (?, ?, ?)
              AND residue > 0""",
        TERMINAL_STATES,
    ).fetchall()
    out = []
    for job_id, residue, terminal_at in rows:
        ts = parse_ts(terminal_at)
        if ts is None:
            continue  # unparseable timestamp: not stale-countable, not hidden — see note in tests
        age = now - ts.timestamp()
        if age >= max_age_seconds:
            out.append(ResidueRow(job_id=str(job_id), residue=int(residue), age_seconds=age))
    return out


def read_db(path: str, now: float, max_age_seconds: float) -> list[ResidueRow] | None:
    """None on failure — a broken check must not mask the disease it watches."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return stale_residues(conn, now, max_age_seconds)
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render(results: dict[str, list[ResidueRow] | None], now: float) -> str:
    """results maps db path → residue rows, or None when the read failed."""
    lines = [
        "# HELP aitbc_escrow_residue_accounts Terminal escrows holding residue older than the alert threshold.",
        "# TYPE aitbc_escrow_residue_accounts gauge",
        "# HELP aitbc_escrow_residue_account One stale residue row.",
        "# TYPE aitbc_escrow_residue_account gauge",
        "# HELP aitbc_escrow_residue_oldest_seconds Age of the oldest stale residue row.",
        "# TYPE aitbc_escrow_residue_oldest_seconds gauge",
        "# HELP aitbc_escrow_residue_scrape_success 1 when the chain.db read worked.",
        "# TYPE aitbc_escrow_residue_scrape_success gauge",
        "# HELP aitbc_escrow_residue_scrape_timestamp_seconds Unix time of this scrape.",
        "# TYPE aitbc_escrow_residue_scrape_timestamp_seconds gauge",
    ]
    total = 0
    oldest = 0.0
    for db, rows in sorted(results.items()):
        ok = rows is not None
        lines.append(f'aitbc_escrow_residue_scrape_success{{db="{_label(db)}"}} {1 if ok else 0}')
        if not ok:
            continue
        for r in rows:
            total += 1
            oldest = max(oldest, r.age_seconds)
            lines.append(f'aitbc_escrow_residue_account{{db="{_label(db)}",job_id="{_label(r.job_id)}"}} 1')
    lines.append(f"aitbc_escrow_residue_accounts {total}")
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
    now = time.time()
    dbs = resolve_dbs()
    results: dict[str, list[ResidueRow] | None] = {}
    rc = 0
    for db in dbs or ["<none>"]:
        if db == "<none>":
            results[db] = None
            rc = 1
            continue
        rows = read_db(db, now, max_age)
        results[db] = rows
        if rows is None:
            rc = 1
    write_atomic(directory, render(results, now))
    return rc


if __name__ == "__main__":
    sys.exit(main())
