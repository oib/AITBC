#!/usr/bin/env python3
"""Sweep service operation ledgers: expire stale pending rows, list or resolve uncertain ones.

Each service that adopts ``aitbc.operations.OperationLedger`` keeps a durable
row per Idempotency-Key. Services run their own periodic reconcile, but this
script is the operator entry point for inspection and manual resolution:

    # Reconcile all known service ledgers and print a report
    python scripts/ops/reconcile-operations.py

    # Inspect operations needing manual resolution
    python scripts/ops/reconcile-operations.py --list-uncertain

    # Mark an uncertain operation resolved (retryable) after checking domain state
    python scripts/ops/reconcile-operations.py --resolve <idempotency-key> --db /path/to/ops.db

    # Purge terminal rows older than N seconds
    python scripts/ops/reconcile-operations.py --purge-seconds 86400

``uncertain`` rows mean a previous attempt's outcome is unknown — resolve
only after confirming via domain state (order book, wallet history, chain)
that the side effect did not land.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aitbc.constants import DATA_DIR  # noqa: E402
from aitbc.operations import OperationLedger  # noqa: E402


def _exchange_db() -> str:
    raw = os.getenv("EXCHANGE_DATABASE_URL", f"sqlite:///{DATA_DIR}/data/exchange/exchange.db")
    if raw.startswith("sqlite:"):
        raw = raw[len("sqlite:") :]
    return "/" + raw.lstrip("/")


def default_ledgers() -> dict[str, str]:
    return {
        "exchange": _exchange_db(),
        "market": os.getenv("MARKET_OPERATIONS_DB")
        or os.getenv("MARKETPLACE_OPERATIONS_DB")
        or str(DATA_DIR / "data" / "market_operations.db"),
        "wallet": os.getenv("WALLET_OPERATIONS_DB") or str(DATA_DIR / "data" / "wallet_operations.db"),
        "coordinator-api": os.getenv("COORDINATOR_OPERATIONS_DB") or str(DATA_DIR / "data" / "coordinator_operations.db"),
    }


def _derive_service(db: str, path_map: dict[str, str]) -> str | None:
    """Service name for a --db path: known ledger path, else the ledger's own
    service column (#1006)."""
    svc = path_map.get(str(Path(db).resolve()))
    if svc is None and Path(db).exists():
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            rows = {r[0] for r in conn.execute("SELECT DISTINCT service FROM operations")}
            conn.close()
            if len(rows) == 1:
                svc = rows.pop()
        except Exception:
            pass
    return svc


def _resolve_targets(args: argparse.Namespace) -> tuple[list[tuple[str, str]], str | None]:
    """--db without --service used to name the ledger after the file stem —
    "market_operations" is a service with no rows, so the run reported
    all-clear over the very uncertainty it was asked to list (#1006)."""
    if not args.db:
        targets = list(default_ledgers().items())
        if args.service:
            # --service on the default set resolves/lists only that ledger —
            # a bare --resolve must not touch every service that holds the
            # key (#1007).
            targets = [(svc, db) for svc, db in targets if svc == args.service]
            if not targets:
                return [], f"error: --service {args.service} is not a known ledger"
        return targets, None
    if args.service:
        return [(args.service, db) for db in args.db], None
    path_map = {str(Path(p).resolve()): svc for svc, p in default_ledgers().items()}
    targets = []
    for db in args.db:
        svc = _derive_service(db, path_map)
        if svc is None:
            return [], f"error: cannot derive service for --db {db} — pass --service"
        targets.append((svc, db))
    return targets, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--db", action="append", default=[], help="Ledger DB path (repeatable); default: all known service ledgers"
    )
    parser.add_argument("--service", help="Service name for --db paths (default: derived per ledger)")
    parser.add_argument("--list-uncertain", action="store_true", help="List operations awaiting manual resolution")
    parser.add_argument("--resolve", metavar="KEY", help="Mark an uncertain operation as resolved (retryable)")
    parser.add_argument("--purge-seconds", type=float, metavar="N", help="Delete completed/failed rows older than N seconds")
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON")
    args = parser.parse_args()


    targets, err = _resolve_targets(args)
    if err:
        print(err, file=sys.stderr)
        return 2

    report: dict[str, dict] = {}
    exit_code = 0
    resolved_any = False
    for service, db in targets:
        if not Path(db).exists():
            report[service] = {"db": db, "skipped": "no ledger file"}
            continue
        ledger = OperationLedger(db, service=service)
        entry: dict = {"db": db}
        entry.update(ledger.reconcile())
        if args.purge_seconds:
            entry["purged"] = ledger.purge(args.purge_seconds)
        if args.resolve:
            entry["resolved"] = ledger.resolve(args.resolve)
            resolved_any = resolved_any or bool(entry["resolved"])
        if args.list_uncertain:
            uncertain = ledger.list_uncertain()
            entry["uncertain"] = [
                {
                    "key": op.idempotency_key,
                    "operation": op.operation_type,
                    "attempt": op.attempt,
                    "error": op.error,
                    "updated_at": op.updated_at,
                }
                for op in uncertain
            ]
        report[service] = entry

    print(json.dumps(report, indent=2, default=str) if args.json else _human(report))
    # exit 1 only when no ledger held the key — a resolve that succeeded in
    # one ledger is a success even where others report not-found (#1007).
    if args.resolve and not resolved_any:
        exit_code = 1
    return exit_code


def _human(report: dict[str, dict]) -> str:
    lines = []
    for service, entry in report.items():
        if "skipped" in entry:
            lines.append(f"{service}: skipped ({entry['skipped']}: {entry['db']})")
            continue
        parts = [
            f"expired→failed={entry.get('expired_to_failed', 0)}",
            f"expired→uncertain={entry.get('expired_to_uncertain', 0)}",
        ]
        if "purged" in entry:
            parts.append(f"purged={entry['purged']}")
        if "resolved" in entry:
            parts.append(f"resolved={'yes' if entry['resolved'] else 'NO — key not uncertain'}")
        if "uncertain" in entry:
            parts.append(f"uncertain_ops={len(entry['uncertain'])}")
            for op in entry["uncertain"]:
                parts.append(f"    {op['key']} {op['operation']} attempt={op['attempt']} error={op['error']}")
        lines.append(f"{service}: " + " ".join(parts))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
