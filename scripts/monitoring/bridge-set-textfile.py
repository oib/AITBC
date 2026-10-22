#!/usr/bin/env python3
"""Export bridge validator-set health as a node_exporter textfile (A36-4).

The bridge release path fails closed when the registered validator set can
no longer meet the multisig threshold — because membership drifted away
from the live consensus attesters (KR-5 left the registered set
empty-intersect). Freshness mirrors the epoch-aware semantics in
bridge_validator.py:461-525: the chain's LATEST epoch is authoritative and
never decays (supersession, not wall time, is the rotation mechanism), so
``aitbc_bridge_set_fresh`` tracks set existence, not age — the raw age
stays visible in ``aitbc_bridge_set_age_seconds``.

Reads the chain DB read-only (SQLite URI mode=ro) and writes, atomically,
to ``<TEXTFILE_DIR>/aitbc_bridge_set.prom``:

    aitbc_bridge_active_validators     active rows in the latest epoch
    aitbc_bridge_possible_signers      active members present in VALIDATOR_SET
    aitbc_bridge_threshold             configured multisig threshold (env)
    aitbc_bridge_set_age_seconds       now - newest registered_at
    aitbc_bridge_set_fresh             1 when a registered set exists
                                       (latest epoch never decays — mirrors
                                       bridge_validator.py:461-525)
    aitbc_bridge_set_scrape_success    1 when the DB read worked
    aitbc_bridge_set_scrape_timestamp_seconds

A DB that cannot be opened reads as failure (scrape_success 0, exit 1) —
a broken check must not mask the disease it watches. LOCKS_PAUSED means
the underlying path is dormant today; the alert text says so — this
matters when locks are re-enabled.

Environment:
    AITBC_CHAIN_DB                      explicit chain.db path (else AITBC_DATA_DIR scan)
    AITBC_DATA_DIR                      default /var/lib/aitbc; scanned for data/*/chain.db
    VALIDATOR_SET                       current consensus validators (JSON list of
                                        addresses or {"address": ...} objects, or
                                        comma-separated addresses)
    BRIDGE_MULTISIG_THRESHOLD           configured threshold (default 2)
    BRIDGE_VALIDATOR_SET_GRACE_PERIOD   freshness window seconds (default 7200)
    AITBC_TEXTFILE_DIR                  default /var/lib/prometheus/node-exporter

Run by a systemd timer (aitbc-bridge-set.timer); stdlib only.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass


@dataclass
class Result:
    db: str
    active: list[str]  # active addresses in latest epoch
    newest_registered_at: float | None  # epoch seconds


def parse_consensus_set(raw: str) -> set[str]:
    """VALIDATOR_SET may be a JSON list or a comma-separated string.

    JSON items may be bare addresses or objects carrying an ``address``
    field (the ``[{"address": ..., "stake": ...}]`` form node env files
    use); anything else is stringified like before.
    """
    raw = raw.strip()
    if not raw:
        return set()
    if raw.startswith("["):
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            items = []
    else:
        items = raw.split(",")
    return {
        a.strip().strip('"').lower()
        for a in (i.get("address", "") if isinstance(i, dict) else str(i) for i in items)
        if a.strip()
    }


def scan_db(db_path: str) -> Result:
    """Read active bridge set + newest registered_at from a chain DB (mode=ro)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        chain_id = conn.execute("SELECT chain_id FROM bridge_validators LIMIT 1").fetchone()
        chain_id = chain_id[0] if chain_id else ""
        epoch_row = conn.execute("SELECT MAX(epoch) FROM bridge_validators WHERE chain_id = ?", (chain_id,)).fetchone()
        epoch = epoch_row[0] if epoch_row and epoch_row[0] is not None else 0
        active = [
            r[0]
            for r in conn.execute(
                "SELECT address FROM bridge_validators WHERE chain_id = ? AND epoch = ? AND is_active = 1",
                (chain_id, epoch),
            )
        ]
        ts_row = conn.execute(
            "SELECT MAX(registered_at) FROM bridge_validators WHERE chain_id = ?",
            (chain_id,),
        ).fetchone()
        newest = _parse_ts(ts_row[0]) if ts_row and ts_row[0] else None
    finally:
        conn.close()
    return Result(db=db_path, active=active, newest_registered_at=newest)


def _parse_ts(raw: str) -> float | None:
    """registered_at is stored as ISO text; accept space or T separator,
    naive (UTC) or offset-aware."""
    from datetime import UTC, datetime

    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


def _is_sqlite_db(path: str) -> bool:
    """True for real SQLite files — zero-byte strays and non-db files that
    land in the scan path (probe artifacts) get skipped, never opened."""
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def find_dbs(explicit: str | None, data_dir: str) -> list[str]:
    """Explicit pin returns strict (bad file -> same failure as always); the
    scan path skips zero-byte and non-sqlite glob hits with a log line."""
    if explicit:
        return [explicit]
    dbs = []
    for p in sorted(glob.glob(os.path.join(data_dir, "data", "*", "chain.db"))):
        if _is_sqlite_db(p):
            dbs.append(p)
        else:
            print(f"bridge-set: skipping non-sqlite glob hit {p}", file=sys.stderr)
    return dbs


def render(results: list[Result], consensus: set[str], threshold: int, grace: int, now: float) -> str:
    lines = []
    active_total = 0
    possible_total = 0
    age = -1.0
    fresh = 0
    for r in results:
        possible = sum(1 for a in r.active if a.lower() in consensus)
        active_total += len(r.active)
        possible_total += possible
        if r.newest_registered_at is not None:
            age = max(age, now - r.newest_registered_at)
    # Mirrors bridge_validator.py:461-525 epoch=None ("the current set")
    # semantics: the latest epoch is authoritative and never decays —
    # supersession, not the clock, retires a set. A readable DB means a
    # latest epoch exists (an empty table is also "fresh" there — the
    # signer count fails first), so fresh follows scrape success.
    # `grace` keeps its rpc meaning — the superseded-epoch window — which
    # this gauge does not exercise.
    fresh = 1 if results else 0
    lines += [
        "# HELP aitbc_bridge_active_validators Active bridge validator rows (latest epoch)",
        "# TYPE aitbc_bridge_active_validators gauge",
        f"aitbc_bridge_active_validators {active_total}",
        "# HELP aitbc_bridge_possible_signers Active members in the current consensus set",
        "# TYPE aitbc_bridge_possible_signers gauge",
        f"aitbc_bridge_possible_signers {possible_total}",
        "# HELP aitbc_bridge_threshold Configured bridge multisig threshold",
        "# TYPE aitbc_bridge_threshold gauge",
        f"aitbc_bridge_threshold {threshold}",
        "# HELP aitbc_bridge_set_age_seconds Seconds since the newest registration row",
        "# TYPE aitbc_bridge_set_age_seconds gauge",
        f"aitbc_bridge_set_age_seconds {age:.0f}",
        "# HELP aitbc_bridge_set_fresh 1 when a registered set exists (latest epoch never decays)",
        "# TYPE aitbc_bridge_set_fresh gauge",
        f"aitbc_bridge_set_fresh {fresh}",
        "# HELP aitbc_bridge_set_scrape_success 1 when the chain DB read worked",
        "# TYPE aitbc_bridge_set_scrape_success gauge",
        f"aitbc_bridge_set_scrape_success {1 if results else 0}",
        "# HELP aitbc_bridge_set_scrape_timestamp_seconds When this run finished",
        "# TYPE aitbc_bridge_set_scrape_timestamp_seconds gauge",
        f"aitbc_bridge_set_scrape_timestamp_seconds {now:.0f}",
    ]
    return "\n".join(lines) + "\n"


def write_atomic(directory: str, text: str) -> None:
    """Write beside the target and rename: node_exporter never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aitbc_bridge_set.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        # node-exporter scrapes as a different user — mkstemp's 0600 would
        # hide the file and mark every scrape an error.
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(directory, "aitbc_bridge_set.prom"))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=os.environ.get("AITBC_CHAIN_DB") or None)
    args = p.parse_args(argv)

    now = time.time()
    data_dir = os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc")
    textfile_dir = os.environ.get("AITBC_TEXTFILE_DIR", "/var/lib/prometheus/node-exporter")
    threshold = int(os.environ.get("BRIDGE_MULTISIG_THRESHOLD", "2"))
    grace = int(os.environ.get("BRIDGE_VALIDATOR_SET_GRACE_PERIOD", "7200"))
    consensus = parse_consensus_set(os.environ.get("VALIDATOR_SET", ""))

    results = []
    for db in find_dbs(args.db, data_dir):
        try:
            results.append(scan_db(db))
        except (sqlite3.Error, OSError):
            continue  # unreadable DB -> scrape_success 0 via empty results

    text = render(results, consensus, threshold, grace, now)
    write_atomic(textfile_dir, text)
    if not results:
        print("bridge-set: no readable chain.db", file=sys.stderr)
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
