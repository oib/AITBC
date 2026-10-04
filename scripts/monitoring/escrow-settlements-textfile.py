#!/usr/bin/env python3
"""Export unlanded-escrow-settlement counts as a node_exporter textfile.

S-8 remedy 3 (detection): ``release_escrow``/``refund_escrow`` mark a row
``released``/``refunded`` at RPC acceptance, but a settlement evaluated before
its lock's block is dropped at production and never re-driven -- the row serves
a dead hash forever. 15 such rows exist fleet-wide (13 releases + 2 refunds),
invisible for weeks because nothing checked inclusion.

The invariant this watches: a row marked ``released`` must have its
``release_tx_hash`` in the sealed ``transaction`` table, and a ``refunded`` row
its ``refund_tx_hash``, within ``AITBC_ESCROW_SETTLEMENT_MAX_AGE_SECONDS``
(default 900s) of the settlement timestamp. A stored ``*_tx_hash`` is itself a
settlement claim -- a two-leg row marked only ``released`` still has its
refund leg checked -- so a leg is claimed by status, timestamp, or hash. The delay threshold is what makes
the check safe: a settlement lands a few blocks after acceptance -- observed
submission-to-lock-block times were <= ~60s, and the largest recorded
release-before-lock gap was 54s -- so 15 minutes is ~15x the anomaly window,
still minutes-fast for a genuine dead hash. A younger unmatched row is simply
in-flight and does not count.

Escrow rows are per-node bookkeeping sharing the consensus chain database, so
the check reads each chain.db found under ``AITBC_DATA_DIR`` (or the explicit
``AITBC_CHAIN_DB``) read-only and unions the findings; run it on every host --
that is why the alert rule lives in the shared ``aitbc_rules.yml`` rather than
the hub-only file.

Writes, atomically, to ``<TEXTFILE_DIR>/aitbc_escrow_settlements.prom``:

    aitbc_escrow_unlanded_settlements                    rows violating the invariant
    aitbc_escrow_unlanded_settlement{job_id=...,kind=...} 1 per violating row
    aitbc_escrow_unlanded_settlement_oldest_seconds      age of the oldest violation
    aitbc_escrow_open_tx_only_locks                      open tx-only locks not in the registry
    aitbc_escrow_open_tx_only_lock{job_id=...}           1 per unregistered open tx-only lock
    aitbc_escrow_settlement_scrape_success{db=...}       1 when the DB read worked
    aitbc_escrow_settlement_scrape_timestamp_seconds     when this run finished

A second scan watches the transaction layer the row check cannot see: an
``ESCROW_LOCK`` transaction with no ``ESCROW_RELEASE``/``ESCROW_REFUND`` leg and
no escrow row is an open tx-only lock -- nothing selects it, nothing settles
it, and without this metric nothing would ever notice a new one. Job ids
listed in the known-artifacts registry (Task 96's six pre-v3 test locks) are
suppressed; every other such lock emits ``aitbc_escrow_open_tx_only_lock``.
The registry is JSON-in-YAML (JSON is valid YAML 1.2, so this stays
stdlib-only); it ships in the repo so every host suppresses the same list.

A DB that cannot be opened or lacks the escrow table reads as failure, not as
"all clear" -- a broken check must not mask the disease it watches. An
unreadable or malformed registry likewise reads as failure (a failing
``scrape_success`` series, exit 1): without it nothing is suppressible, and
emitting the raw unsuppressed list would false-alert on every known lock.
Run by a systemd timer (aitbc-escrow-settlements.timer); stdlib only.

Environment:
    AITBC_CHAIN_DB                          explicit chain.db path (else scan below)
    AITBC_DATA_DIR                          default /var/lib/aitbc; scanned for data/*/chain.db
    AITBC_ESCROW_SETTLEMENT_MAX_AGE_SECONDS default 900
    AITBC_TEXTFILE_DIR                      default /var/lib/prometheus/node-exporter
    AITBC_ESCROW_KNOWN_ARTIFACTS            known-artifact registry path;
                                            default escrow-known-artifacts.yml beside this script
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from typing import NamedTuple

OUTPUT_NAME = "aitbc_escrow_settlements.prom"
DEFAULT_MAX_AGE_SECONDS = 900


# NamedTuple, not @dataclass: the test suite importlib-loads this script without
# registering it in sys.modules, and dataclass field resolution requires the
# module entry under Python 3.13.
class Violation(NamedTuple):
    job_id: str
    kind: str  # "release" | "refund"
    age_seconds: float


def find_chain_dbs(data_dir: str) -> list[str]:
    """Every ``data/*/chain.db`` under the data dir, sorted for determinism."""
    return sorted(glob.glob(os.path.join(data_dir, "data", "*", "chain.db")))


def parse_settled_at(raw: object) -> datetime | None:
    """Parse a settlement timestamp stored by SQLAlchemy's sqlite DATETIME.

    Stored forms seen in the fleet: 'YYYY-MM-DD HH:MM:SS.ffffff' (space form,
    the default render) and ISO with 'T'/'Z'. Naive values are UTC. Anything
    else returns None -- the caller treats a missing timestamp as a violation,
    since a row that claims settled without a legible timestamp is broken.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _unlanded_rows(conn: sqlite3.Connection, now: float, max_age_seconds: float) -> list[Violation]:
    """Escrow legs whose stored settlement hash is not sealed.

    A leg is claimed three ways: a terminal ``status``, a settlement
    timestamp, or a stored ``*_tx_hash`` -- a hash is itself the claim, so a
    two-leg row marked only ``released`` still has its refund leg checked.
    """
    violations: list[Violation] = []
    rows = conn.execute(
        "SELECT job_id, status, release_tx_hash, refund_tx_hash, released_at, refunded_at "
        "FROM escrow "
        "WHERE status IN ('released', 'refunded') OR released_at IS NOT NULL OR refunded_at IS NOT NULL "
        "OR release_tx_hash IS NOT NULL OR refund_tx_hash IS NOT NULL"
    ).fetchall()

    def stored(tx_hash: object) -> bool:
        return isinstance(tx_hash, str) and bool(tx_hash.strip())

    def sealed(tx_hash: object) -> bool:
        if not isinstance(tx_hash, str) or not tx_hash:
            return False
        # Per-hash probe: the sealed table is far larger than the settled-row
        # set, so probing each claim beats loading every tx_hash into memory.
        return conn.execute("SELECT 1 FROM 'transaction' WHERE tx_hash = ? LIMIT 1", (tx_hash,)).fetchone() is not None

    for job_id, status, release_hash, refund_hash, released_at, refunded_at in rows:
        legs = []
        if status == "released" or released_at is not None or stored(release_hash):
            legs.append(("release", release_hash, released_at))
        if status == "refunded" or refunded_at is not None or stored(refund_hash):
            legs.append(("refund", refund_hash, refunded_at))
        for kind, tx_hash, settled_raw in legs:
            if sealed(tx_hash):
                continue
            settled_at = parse_settled_at(settled_raw)
            age = float("inf") if settled_at is None else now - settled_at.timestamp()
            if age > max_age_seconds:
                violations.append(Violation(job_id=job_id, kind=kind, age_seconds=age))
    return violations


def read_db(path: str, now: float, max_age_seconds: float) -> list[Violation] | None:
    """Violations in one chain.db, or None when the DB could not be checked."""
    try:
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
            return _unlanded_rows(conn, now, max_age_seconds)
    except sqlite3.Error:
        return None


def read_known_artifacts(path: str) -> set[str] | None:
    """Job ids in the known-artifact registry, or None when it cannot be trusted.

    The file is JSON-in-YAML so stdlib json parses it. Any failure -- missing
    file, unreadable content, wrong shape -- returns None; the caller turns
    that into a scrape failure rather than an unsuppressed all-clear.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        artifacts = data["artifacts"]
        known = {entry["job_id"] for entry in artifacts}
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not all(isinstance(job_id, str) and job_id for job_id in known):
        return None
    return known


def read_open_locks(path: str, known: set[str]) -> set[str] | None:
    """Open tx-only locks in one chain.db, minus the registry; None on failure.

    Open tx-only = ESCROW_LOCK tx, no ESCROW_RELEASE/ESCROW_REFUND leg, no
    escrow row. The NOT IN subqueries exclude NULL job ids explicitly -- a
    NULL in an IN-list would quietly empty the whole result.
    """
    query = """
        SELECT job_id FROM (
            SELECT DISTINCT json_extract(payload, '$.job_id') AS job_id
            FROM 'transaction' WHERE type = 'ESCROW_LOCK'
        )
        WHERE job_id IS NOT NULL
          AND job_id NOT IN (
              SELECT json_extract(payload, '$.job_id') FROM 'transaction'
              WHERE type IN ('ESCROW_RELEASE', 'ESCROW_REFUND')
                AND json_extract(payload, '$.job_id') IS NOT NULL
          )
          AND job_id NOT IN (SELECT job_id FROM escrow WHERE job_id IS NOT NULL)
    """
    try:
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
            return {row[0] for row in conn.execute(query)} - known
    except sqlite3.Error:
        return None


def _label(value: str) -> str:
    """A label value that cannot break the exposition format."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render(
    results: dict[str, list[Violation] | None],
    now: float,
    open_locks: set[str] | None = None,
    failed_sources: list[str] | None = None,
) -> str:
    violations = [v for vs in results.values() if vs for v in vs]
    lines = [
        "# HELP aitbc_escrow_unlanded_settlements Escrow rows marked released/refunded whose "
        "settlement hash is absent from the sealed transaction table past the age threshold.",
        "# TYPE aitbc_escrow_unlanded_settlements gauge",
        f"aitbc_escrow_unlanded_settlements {len(violations)}",
        "# HELP aitbc_escrow_unlanded_settlement Per-job detail of aitbc_escrow_unlanded_settlements.",
        "# TYPE aitbc_escrow_unlanded_settlement gauge",
    ]
    for v in sorted(violations, key=lambda v: (v.job_id, v.kind)):
        lines.append(f'aitbc_escrow_unlanded_settlement{{job_id="{_label(v.job_id)}",kind="{v.kind}"}} 1')
    lines += [
        "# HELP aitbc_escrow_unlanded_settlement_oldest_seconds Age of the oldest unlanded settlement; 0 when none.",
        "# TYPE aitbc_escrow_unlanded_settlement_oldest_seconds gauge",
    ]
    oldest = max((v.age_seconds for v in violations), default=0)
    lines.append(f"aitbc_escrow_unlanded_settlement_oldest_seconds {int(oldest)}")
    locks = sorted(open_locks or set())
    lines += [
        "# HELP aitbc_escrow_open_tx_only_locks ESCROW_LOCK transactions with no settlement leg and no "
        "escrow row, minus the known-artifacts registry.",
        "# TYPE aitbc_escrow_open_tx_only_locks gauge",
        f"aitbc_escrow_open_tx_only_locks {len(locks)}",
        "# HELP aitbc_escrow_open_tx_only_lock Per-job detail of aitbc_escrow_open_tx_only_locks.",
        "# TYPE aitbc_escrow_open_tx_only_lock gauge",
    ]
    for job_id in locks:
        lines.append(f'aitbc_escrow_open_tx_only_lock{{job_id="{_label(job_id)}"}} 1')
    lines += [
        "# HELP aitbc_escrow_settlement_scrape_success 1 when this source was readable and carried the escrow table.",
        "# TYPE aitbc_escrow_settlement_scrape_success gauge",
    ]
    for db, result in sorted(results.items()):
        lines.append(f'aitbc_escrow_settlement_scrape_success{{db="{_label(db)}"}} {0 if result is None else 1}')
    for source in failed_sources or []:
        lines.append(f'aitbc_escrow_settlement_scrape_success{{db="{_label(source)}"}} 0')
    lines += [
        "# HELP aitbc_escrow_settlement_scrape_timestamp_seconds Unix time the last run finished.",
        "# TYPE aitbc_escrow_settlement_scrape_timestamp_seconds gauge",
        f"aitbc_escrow_settlement_scrape_timestamp_seconds {int(now)}",
    ]
    return "\n".join(lines) + "\n"


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_escrow_settlements.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(directory, OUTPUT_NAME))
    except BaseException:
        os.unlink(tmp)
        raise


def resolve_dbs() -> list[str]:
    explicit = os.environ.get("AITBC_CHAIN_DB", "").strip()
    if explicit:
        return [explicit]
    return find_chain_dbs(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc"))


def main() -> int:
    try:
        max_age = float(os.environ.get("AITBC_ESCROW_SETTLEMENT_MAX_AGE_SECONDS", str(DEFAULT_MAX_AGE_SECONDS)))
    except ValueError:
        print("escrow-settlements: AITBC_ESCROW_SETTLEMENT_MAX_AGE_SECONDS is not a number", file=sys.stderr)
        return 2
    directory = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    registry_path = os.environ.get("AITBC_ESCROW_KNOWN_ARTIFACTS", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "escrow-known-artifacts.yml"
    )
    dbs = resolve_dbs()
    now = time.time()
    if not dbs:
        # Still write the textfile: with absent() gone from the rules, a host
        # that stops writing entirely would be invisible. scrape_success{db=
        # "none"} 0 leaves a failing series for the alert to fire on.
        write_atomic(directory, render({"none": None}, now))
        print("escrow-settlements: no chain.db found to check", file=sys.stderr)
        return 2
    known = read_known_artifacts(registry_path)
    results: dict[str, list[Violation] | None] = {}
    open_locks: set[str] = set()
    for db in dbs:
        violations = read_db(db, now, max_age)
        if violations is None:
            results[db] = None
            continue
        if known is not None:
            opened = read_open_locks(db, known)
            if opened is None:
                results[db] = None
                continue
            open_locks |= opened
        results[db] = violations
    # When the registry is unreadable the open-lock scan is skipped entirely:
    # without suppression every known artifact would false-alert, so the scan
    # emits nothing and the registry's own scrape_success carries the failure.
    failed_sources = [] if known is not None else [registry_path]
    write_atomic(directory, render(results, now, open_locks=open_locks, failed_sources=failed_sources))
    failed = [db for db, result in results.items() if result is None]
    if known is None:
        failed.append(registry_path)
    if failed:
        print(f"escrow-settlements: could not check {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
