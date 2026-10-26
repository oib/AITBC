#!/usr/bin/env python3
"""ESCROW-STUCK-SWEEP-1 — read-only monitor for escrows still locked after a terminal job.

An escrow row whose ``status`` is still ``locked`` while its job has reached a
terminal state is money no automatic path will ever settle: SEC-20b left
0.0001 AIT behind that way, and the #455 run showed a fast job can strand a
lock. Nothing alerted on either. This sweep lists them.

Reads — and only reads:

* the chain DB ``escrow`` table (locked rows, lock age, ``job_tx_hash``), plus
  the ``transaction`` table for a sealed ``ESCROW_RELEASE``/``ESCROW_REFUND``
  leg the row has not caught up with;
* the coordinator DB ``job``/``job_payments`` tables when present
  (``job.state`` in ``COMPLETED``/``FAILED``/``CANCELED``/``EXPIRED`` is the
  authoritative terminal signal; ``job_payments.status`` in
  ``released``/``refunded``/``settlement_failed`` is secondary evidence);
* the marketplace DB ``marketplace_jobs`` table when present (same state
  vocabulary — marketplace jobs such as ``sw_job_*`` often have no
  coordinator row at all).

Every connection is SQLite ``mode=ro`` + ``PRAGMA query_only=ON`` — the same
guarantee ``rebuild-escrows.py`` gives. ``--host hub`` runs the identical
read-only queries over ``ssh hub sqlite3 -json 'file:...?mode=ro'`` so the
sweep can run from the IDE host without a copy of the database; nothing is
ever written, locally or remotely.

A locked escrow whose job is terminal AND whose lock is older than
``--max-age`` (default 3600 s, like the acceptance window) is *stuck*: the
script prints one row per stuck lock, then every other still-locked escrow
as information, and exits 1 when at least one stuck row exists (0 = clean,
2 = a data source could not be read — a broken check must not read as
"all clear").

Optional ``--textfile`` writes an atomic node_exporter file mirroring the
escrow-settlements textfile conventions:

    aitbc_escrow_stuck_locks                        count of stuck locks
    aitbc_escrow_stuck_lock{job_id=...}             1 per stuck lock
    aitbc_escrow_stuck_lock_oldest_seconds          age of the oldest stuck lock
    aitbc_escrow_stuck_scrape_success{db=...}       1 when the DB read worked
    aitbc_escrow_stuck_scrape_timestamp_seconds     when this run finished

Run by hand or from the gate — deliberately no systemd unit.

Usage::

    escrow-stuck-sweep.py                                # local defaults
    escrow-stuck-sweep.py --host hub                     # read hub over ssh
    escrow-stuck-sweep.py --chain-db chain.db \
        --coordinator-db coordinator.db --max-age 7200
    escrow-stuck-sweep.py --json                         # machine-readable

Environment:
    AITBC_DATA_DIR            default /var/lib/aitbc; ``data/*/chain.db``,
                              ``data/coordinator.db`` and
                              ``data/marketplace_service.db`` are derived from it
    AITBC_CHAIN_DB            explicit chain.db path (else scan data/*/chain.db)
    AITBC_COORDINATOR_DB      explicit coordinator.db path
    AITBC_MARKETPLACE_DB      explicit marketplace_service.db path
    AITBC_ESCROW_STUCK_MAX_AGE_SECONDS   default --max-age (3600)
    AITBC_TEXTFILE_DIR        default dir for --textfile
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Terminal job states — coordinator ``job.state`` and ``marketplace_jobs.state``
# share this vocabulary (services/jobs.py: COMPLETED, FAILED, CANCELED, EXPIRED;
# CANCELED is the American spelling the code writes).
TERMINAL_JOB_STATES = frozenset({"COMPLETED", "FAILED", "CANCELED", "EXPIRED"})

# job_payments.status values that prove settlement is over even when the job
# row itself is missing or still mid-state.
TERMINAL_PAYMENT_STATES = frozenset({"released", "refunded", "settlement_failed"})

DATA_DIR = os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc")

_ESCROW_COLS = (
    "job_id",
    "chain_id",
    "buyer",
    "provider",
    "amount",
    "status",
    "created_at",
    "released_at",
    "refunded_at",
    "job_tx_hash",
)


def _open_ro(db_path: str) -> sqlite3.Connection:
    """The ONLY local connection this program creates: mode=ro + query_only.

    Same pattern as ``rebuild-escrows.py`` — no ``immutable=1``, a live
    chain.db keeps newest pages in the WAL and immutable mode would read a
    stale snapshot.
    """
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _sql_quote(value: Any) -> str:
    """Literal-quote one value for an ssh-side sqlite3 command line."""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _remote_query(host: str, db_path: str, sql: str) -> list[dict[str, Any]]:
    """Run one read-only query on a remote host via ``ssh <host> sqlite3 -json``.

    The remote sqlite3 opens the ``mode=ro`` URI itself, so the read-only
    guarantee holds on the far side exactly as it does locally.
    """
    # The remote login shell may be zsh: join and quote the remote side as one
    # command string so the '?' in the mode=ro URI is never glob-parsed.
    remote_cmd = " ".join(shlex.quote(a) for a in ["sqlite3", "-json", f"file:{db_path}?mode=ro", sql])
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        host,
        remote_cmd,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"remote sqlite3 on {host}:{db_path} failed: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    return json.loads(out) if out else []


class Source:
    """One database, local or reached over ssh; query() returns dict rows."""

    def __init__(self, path: str, host: str | None = None) -> None:
        self.path = path
        self.host = host

    def label(self) -> str:
        return f"{self.host}:{self.path}" if self.host else self.path

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if self.host:
            for value in params:
                needle = "?"
                sql = sql.replace(needle, _sql_quote(value), 1)
            return _remote_query(self.host, self.path, sql)
        conn = _open_ro(self.path)
        try:
            cur = conn.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
        finally:
            conn.close()

    def table_cols(self, table: str) -> set[str] | None:
        """Column names of ``table``; None when the db/table is unreadable."""
        try:
            rows = self.query(f'PRAGMA table_info("{table}")')
        except Exception:
            return None
        return {r["name"] for r in rows}


def _parse_ts(raw: Any) -> datetime | None:
    """Parse the ``YYYY-MM-DD HH:MM:SS.ffffff`` / ISO timestamps the services write."""
    if raw in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def locked_escrows(chain: Source) -> list[dict[str, Any]]:
    """All escrow rows still holding funds: status='locked', no settle timestamp."""
    cols = chain.table_cols("escrow")
    if cols is None:
        raise RuntimeError(f"cannot read escrow table in {chain.label()}")
    wanted = [c for c in _ESCROW_COLS if c in cols]
    sql = f"SELECT {', '.join(wanted)} FROM escrow WHERE status = 'locked' AND released_at IS NULL AND refunded_at IS NULL"
    return chain.query(sql)


def settled_txs(chain: Source) -> set[str]:
    """job_ids with a sealed ESCROW_RELEASE/ESCROW_REFUND leg on this chain."""
    if chain.table_cols("transaction") is None:
        return set()
    rows = chain.query("SELECT tx_metadata, payload FROM \"transaction\" WHERE type IN ('ESCROW_RELEASE','ESCROW_REFUND')")
    out: set[str] = set()
    for row in rows:
        for blob in (row.get("tx_metadata"), row.get("payload")):
            if not blob:
                continue
            try:
                meta = json.loads(blob)
            except (TypeError, ValueError):
                continue
            jid = meta.get("job_id") or (meta.get("escrow") or {}).get("job_id")
            if jid:
                out.add(str(jid))
    return out


def job_states(db: Source | None, job_ids: list[str]) -> dict[str, str]:
    """job_id -> state from coordinator ``job`` or ``marketplace_jobs``."""
    if db is None or not job_ids:
        return {}
    if db.table_cols("job") is not None:
        table, id_col, state_col = "job", "id", "state"
    elif db.table_cols("marketplace_jobs") is not None:
        table, id_col, state_col = "marketplace_jobs", "id", "state"
    else:
        return {}
    out: dict[str, str] = {}
    for jid in job_ids:
        try:
            rows = db.query(f"SELECT {state_col} AS s FROM {table} WHERE {id_col} = ?", (jid,))
        except Exception:
            continue
        if rows and rows[0].get("s"):
            out[jid] = str(rows[0]["s"])
    return out


def payment_states(coord: Source | None, job_ids: list[str]) -> dict[str, str]:
    """job_id -> job_payments.status (secondary terminal evidence)."""
    if coord is None or not job_ids or coord.table_cols("job_payments") is None:
        return {}
    out: dict[str, str] = {}
    for jid in job_ids:
        try:
            rows = coord.query("SELECT status AS s FROM job_payments WHERE job_id = ?", (jid,))
        except Exception:
            continue
        if rows and rows[0].get("s"):
            out[jid] = str(rows[0]["s"])
    return out


def classify(
    escrows: list[dict[str, Any]],
    *,
    jobs: dict[str, str],
    payments: dict[str, str],
    settled: set[str],
    max_age: float,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split locked escrows into (stuck, other) rows for display."""
    stuck: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for esc in escrows:
        jid = str(esc["job_id"])
        created = _parse_ts(esc.get("created_at"))
        age = (now - created).total_seconds() if created else None
        job_state = jobs.get(jid)
        payment_state = payments.get(jid)
        on_chain_terminal = jid in settled or bool(esc.get("job_tx_hash"))
        if job_state:
            job_status: str = job_state
            terminal = job_state in TERMINAL_JOB_STATES
            source = "job.state"
        elif payment_state:
            job_status = f"payment:{payment_state}"
            terminal = payment_state in TERMINAL_PAYMENT_STATES
            source = "job_payments.status"
        elif on_chain_terminal:
            job_status = "sealed-settlement" if jid in settled else "job_tx_hash set"
            terminal = True
            source = "chain tx"
        else:
            job_status = "unknown"
            terminal = False
            source = "-"
        row = {
            "job_id": jid,
            "chain_id": esc.get("chain_id"),
            "amount": esc.get("amount"),
            "created_at": str(esc.get("created_at") or ""),
            "age_seconds": age,
            "job_status": job_status,
            "terminal_source": source,
        }
        if terminal and age is not None and age > max_age:
            stuck.append(row)
        else:
            other.append(row)
    return stuck, other


def _print_table(title: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    print(f"\n{title} ({len(rows)}):")
    hdr = f"{'job_id':<40} {'amount_units':>12} {'age':>10} {'job_status':<22} evidence"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        age = f"{r['age_seconds']:.0f}s" if r["age_seconds"] is not None else "?"
        print(f"{r['job_id']:<40} {r['amount']:>12} {age:>10} {r['job_status']:<22} {r['terminal_source']}")


def _write_textfile(path: Path, stuck: list[dict[str, Any]], ok_dbs: list[str], now: datetime) -> None:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    lines = [
        "# HELP aitbc_escrow_stuck_locks Escrows locked while their job is terminal past max-age.",
        "# TYPE aitbc_escrow_stuck_locks gauge",
        f"aitbc_escrow_stuck_locks {len(stuck)}",
    ]
    for r in stuck:
        lines.append(f'aitbc_escrow_stuck_lock{{job_id="{esc(r["job_id"])}"}} 1')
    if stuck:
        oldest = max(r["age_seconds"] or 0 for r in stuck)
        lines.append(f"aitbc_escrow_stuck_lock_oldest_seconds {oldest:.0f}")
    for db in ok_dbs:
        lines.append(f'aitbc_escrow_stuck_scrape_success{{db="{esc(db)}"}} 1')
    lines.append(f"aitbc_escrow_stuck_scrape_timestamp_seconds {int(now.timestamp())}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="List escrows still locked after a terminal job (read-only).",
        epilog="exit 1 = stuck locks found, 0 = clean, 2 = a data source was unreadable",
    )
    p.add_argument(
        "--host", choices=["local", "hub"], default="local", help="'hub' runs the same read-only queries over ssh hub"
    )
    p.add_argument(
        "--chain-db",
        default=os.environ.get("AITBC_CHAIN_DB"),
        help="chain.db path (default: scan $AITBC_DATA_DIR/data/*/chain.db)",
    )
    p.add_argument(
        "--coordinator-db",
        default=os.environ.get("AITBC_COORDINATOR_DB"),
        help=f"coordinator.db path (default: {DATA_DIR}/data/coordinator.db if present)",
    )
    p.add_argument(
        "--marketplace-db",
        default=os.environ.get("AITBC_MARKETPLACE_DB"),
        help=f"marketplace db path (default: {DATA_DIR}/data/marketplace_service.db if present)",
    )
    p.add_argument(
        "--max-age",
        type=float,
        default=float(os.environ.get("AITBC_ESCROW_STUCK_MAX_AGE_SECONDS", "3600")),
        help="seconds a lock may outlive its terminal job before it counts (default 3600)",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument(
        "--textfile", metavar="PATH", help="write node_exporter metrics to PATH (atomic); default dir $AITBC_TEXTFILE_DIR"
    )
    args = p.parse_args(argv)

    ssh_host = "hub" if args.host == "hub" else None
    remote = ssh_host is not None

    chain_dbs: list[str]
    if args.chain_db:
        chain_dbs = [args.chain_db]
    elif remote:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", str(ssh_host), f"ls {shlex.quote(DATA_DIR)}/data/*/chain.db 2>/dev/null"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        chain_dbs = [ln for ln in proc.stdout.split() if ln.endswith("chain.db")]
    else:
        chain_dbs = sorted(str(p) for p in Path(DATA_DIR).glob("data/*/chain.db"))
    if not chain_dbs:
        print("error: no chain.db found — pass --chain-db", file=sys.stderr)
        return 2

    coord_path = args.coordinator_db or f"{DATA_DIR}/data/coordinator.db"
    market_path = args.marketplace_db or f"{DATA_DIR}/data/marketplace_service.db"

    def usable(path: str) -> bool:
        if remote:
            proc = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", str(ssh_host), "test", "-f", path],
                capture_output=True,
                timeout=30,
            )
            return proc.returncode == 0
        return Path(path).is_file()

    coord = Source(coord_path, ssh_host) if usable(coord_path) else None
    market = Source(market_path, ssh_host) if usable(market_path) else None
    if coord is None and market is None:
        print(
            "note: no coordinator.db or marketplace_service.db found — job status falls back to on-chain evidence only",
            file=sys.stderr,
        )

    now = datetime.now(UTC)
    all_stuck: list[dict[str, Any]] = []
    all_other: list[dict[str, Any]] = []
    ok_dbs: list[str] = []
    failures = 0
    job_ids_seen: set[str] = set()
    escrows_all: list[dict[str, Any]] = []
    settled_all: set[str] = set()

    for cdb in chain_dbs:
        chain = Source(cdb, ssh_host)
        try:
            rows = locked_escrows(chain)
            settled_all |= settled_txs(chain)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            failures += 1
            continue
        ok_dbs.append(chain.label())
        for r in rows:
            if str(r["job_id"]) in job_ids_seen:
                continue
            job_ids_seen.add(str(r["job_id"]))
            escrows_all.append(r)

    job_ids = list(job_ids_seen)
    jobs = job_states(coord, job_ids)
    jobs.update({k: v for k, v in job_states(market, job_ids).items() if k not in jobs})
    payments = payment_states(coord, job_ids)

    stuck, other = classify(
        escrows_all,
        jobs=jobs,
        payments=payments,
        settled=settled_all,
        max_age=args.max_age,
        now=now,
    )
    all_stuck, all_other = stuck, other

    if args.json:
        print(
            json.dumps(
                {"stuck": all_stuck, "locked_other": all_other, "dbs_read": ok_dbs, "failures": failures},
                indent=2,
                default=str,
            )
        )
    else:
        print(
            f"escrow-stuck-sweep — {now.isoformat(timespec='seconds')} — "
            f"max-age {args.max_age:.0f}s — {len(job_ids)} locked escrow(s) "
            f"across {len(ok_dbs)} chain db(s)"
        )
        _print_table("STUCK — locked after terminal job", all_stuck)
        _print_table("still locked (job active or within age grace)", all_other)
        if not all_stuck and not all_other:
            print("no locked escrows")

    if args.textfile:
        out = Path(args.textfile)
        if out.is_dir() or str(args.textfile).endswith("/"):
            out = out / "aitbc_escrow_stuck.prom"
        _write_textfile(out, all_stuck, ok_dbs, now)
        print(f"textfile written: {out}")

    if failures:
        return 2
    return 1 if all_stuck else 0


if __name__ == "__main__":
    sys.exit(main())
