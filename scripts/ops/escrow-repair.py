#!/usr/bin/env python3
"""SD-1 escrow write-phase tool — flag-gated, separate from the proof.

``rebuild-escrows.py`` is the read-only proof: it derives the escrow table
from sealed chain history and reports every stored row that contradicts it.
This tool is the write side. It does two things:

* ``snapshot`` — copy a chain.db into a scratch directory via the sqlite
  backup API while the source is held open read-only (mode=ro +
  query_only), and print the source sha256. The snapshot is the rollback
  artifact for the write phase AND the scratch copy this round's
  verification runs on.
* ``apply`` — perform the reconciliation writes on a *copy*: class-1
  inserts (rows missing but derivable from sealed txs), class-2 updates
  (deferred-residue: released_amount/release_tx_hash catching up to
  additional sealed legs), and the orphan archive (stored rows with no
  sealed lock are moved to an ``escrow_orphan`` shadow table, preserving
  their non-derivable RPC-era fields — operator decision 2026-10-12,
  option B). Then the proof is re-run on the same connection and the
  post-write plan printed.

Gates — all must pass for a byte to be written:

1. ``apply`` refuses unless ``--write`` is given (default is a dry run
   that prints the plan, equivalent to ``rebuild-escrows.py --plan``).
2. ``apply --write`` refuses outright when the target resolves inside the
   live data directory (default ``/var/lib/aitbc``, overridable with
   ``AITBC_DATA_DIR``); a live write additionally requires
   ``--allow-live-path``, which is deliberately not exercised this round.
3. A reconcile abort (an unreviewed R2 double-settlement) blocks apply
   even on a copy — the abort reasons print verbatim.

A job tagged ``[known anomaly]`` in the plan IS written on the copy: the
operator's "record truth + anomaly" decision means the row records the
chain's (overpaid) truth; the anomaly stays flagged in output so the
separate remedy decision is not silently absorbed into the routine
update path. On a live run this behavior must be re-reviewed by the
operator.

Verification run (this round): snapshot node2's chain.db onto node1
scratch (dir mode 700), apply on the copy, delete the copy afterwards.
No live database is written.

Usage::

    escrow-repair.py snapshot --db /path/chain.db --to /scratch/dir
    escrow-repair.py apply   --db /scratch/dir/chain.db            # dry run
    escrow-repair.py apply   --db /scratch/dir/chain.db --write    # gated write
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# The derivation machinery lives in the proof tool; load it as a module so
# the writer applies exactly the rows the proof derived — never a second,
# divergent implementation.
_REBUILD = Path(__file__).resolve().with_name("rebuild-escrows.py")
_spec = importlib.util.spec_from_file_location("rebuild_escrows", _REBUILD)
_reb = importlib.util.module_from_spec(_spec)
sys.modules["rebuild_escrows"] = _reb
_spec.loader.exec_module(_reb)  # type: ignore[union-attr]

LIVE_DATA_DIR = Path(os.environ.get("AITBC_DATA_DIR", "/var/lib/aitbc")).resolve()

# Escrow columns the chain derives. Anything else in the stored schema
# (job_tx_hash, energy_quote_snapshot, energy_net_floor_units,
# energy_provider_credit_units, energy_fee_basis_points, billed_legs,
# protected) is RPC-era bookkeeping the chain never carried: inserts leave
# them NULL except ``protected`` (NOT NULL on the live schema → 0).
_DERIVED_COLS = (
    "job_id",
    "chain_id",
    "buyer",
    "provider",
    "amount",
    "status",
    "created_at",
    "released_at",
    "refunded_at",
    "lock_tx_hash",
    "release_tx_hash",
    "refund_tx_hash",
    "released_amount",
    "refunded_amount",
    "energy_quote_id",
    "energy_quote_digest",
    "energy_settlement_route",
    "energy_settlement_asset",
    "energy_settlement_unit_scale",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_db(src: Path, dst_dir: Path) -> dict[str, Any]:
    """Copy src into dst_dir via the sqlite backup API, source held read-only."""
    dst_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    dst_dir.chmod(0o700)
    dst = dst_dir / "chain.db"
    if dst.exists():
        raise SystemExit(f"refusing to overwrite existing snapshot copy: {dst}")
    src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    src_conn.execute("PRAGMA query_only=ON")
    dst_conn = sqlite3.connect(dst)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return {
        "src": str(src),
        "dst": str(dst),
        "src_sha256": _sha256(src),
        "dst_sha256": _sha256(dst),
        "src_bytes": src.stat().st_size,
        "dst_bytes": dst.stat().st_size,
    }


def _ensure_orphan_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS escrow_orphan AS "
        "SELECT *, NULL AS archived_at, NULL AS archived_reason FROM escrow WHERE 0"
    )


def apply_plan(conn: sqlite3.Connection, report: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Apply insert / update / orphan-archive classes inside one transaction.

    Returns per-class counts and the list of written job_ids (shortened).
    Raises on any abort reason — caller prints and exits.
    """
    if plan["abort"]:
        raise SystemExit("apply blocked — reconcile abort:\n  " + "\n  ".join(plan["abort"]))
    jobs = report.get("jobs", {})
    # The plan summary does not carry the full derived row; re-derive the
    # insert set with the proof's own machinery so the written row is
    # byte-identical to what the proof derived.
    blocks = _reb._load_blocks(conn)
    canonical = _reb._canonical_heights(blocks)
    legs_by_job: dict[str, list[dict[str, Any]]] = {}
    for leg in _reb._load_legs(conn):
        if leg["job_id"] is not None:
            legs_by_job.setdefault(leg["job_id"], []).append(leg)
    written: dict[str, Any] = {"insert": [], "update": [], "archive": [], "anomaly_written": []}
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        # Class 1 — inserts for jobs with sealed locks but no stored row.
        cols = ", ".join(_DERIVED_COLS) + ", protected"
        marks = ", ".join("?" for _ in _DERIVED_COLS) + ", 0"
        for item in plan["insert"]:
            jid = item["job_id"]
            cid = jobs[jid]["chain_id"]
            derived = _reb._derive_job(cid, jid, legs_by_job.get(jid, []), blocks, canonical)
            row = [jid, cid] + [derived.get(c) for c in _DERIVED_COLS[2:]]
            # cols/marks are built from the _DERIVED_COLS constant — fixed identifiers, values bound
            cur.execute(f"INSERT INTO escrow ({cols}) VALUES ({marks})", row)  # nosec
            written["insert"].append(jid)

        # Class 2 — deferred-residue updates, field-for-field from the plan.
        for item in plan["update"]:
            jid = item["job_id"]
            for s in item["set"]:
                # s['field'] comes from the plan's conflict fields — drawn from the
                # proof's EXACT_FIELDS whitelist, never user input; the value is bound
                cur.execute(
                    f"UPDATE escrow SET {s['field']} = ? WHERE job_id = ?",  # nosec
                    (s["derived"], jid),
                )
            written["update"].append(jid)
            if item.get("anomaly"):
                written["anomaly_written"].append(jid)

        _archive_orphans(cur, conn, plan, written)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return written


def _archive_orphans(cur: sqlite3.Cursor, conn: sqlite3.Connection, plan: dict[str, Any], written: dict[str, Any]) -> None:
    """Class 3 — preserve each orphan row verbatim in escrow_orphan, then
    remove it from escrow (operator option B: archive, not delete)."""
    _ensure_orphan_table(conn)
    for item in plan["report_only"]:
        if item.get("class") != "orphan-row":
            continue
        jid, cid = item["job_id"], item["chain_id"]
        cur.execute(
            "INSERT INTO escrow_orphan SELECT *, datetime('now'), 'no sealed lock leg' "
            "FROM escrow WHERE job_id = ? AND chain_id = ?",
            (jid, cid),
        )
        cur.execute("DELETE FROM escrow WHERE job_id = ? AND chain_id = ?", (jid, cid))
        written["archive"].append(jid)


def _print_apply_summary(written: dict[str, Any]) -> None:
    short = _reb._short
    for cls in ("insert", "update", "archive"):
        ids = written[cls]
        print(f"  {cls}: {len(ids)} row(s)" + ("" if not ids else " — " + ", ".join(short(j) for j in ids)))
    for jid in written["anomaly_written"]:
        print(f"  [known anomaly] job={short(jid)} written with chain truth — separate remedy decision pending")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SD-1 escrow write phase — gated; default is dry-run.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="copy a chain.db read-only via the sqlite backup API")
    snap.add_argument("--db", required=True, help="source chain.db (opened mode=ro)")
    snap.add_argument("--to", required=True, help="scratch directory (created mode 700)")
    apply_p = sub.add_parser("apply", help="reconcile-write an escrow table on a copy")
    apply_p.add_argument("--db", required=True, help="target chain.db — a snapshot copy")
    apply_p.add_argument("--write", action="store_true", help="perform the writes (default: dry-run plan)")
    apply_p.add_argument(
        "--allow-live-path",
        action="store_true",
        help="permit --write under the live data dir — operator-gated, not used this round",
    )
    apply_p.add_argument("--json", action="store_true", help="emit the pre/post plans as JSON")
    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        src = Path(args.db).resolve()
        if not src.is_file():
            print(f"source not found: {src}", file=sys.stderr)
            return 2
        info = snapshot_db(src, Path(args.to).resolve())
        print("snapshot complete (source read-only via backup API):")
        print(f"  src      {info['src']}  ({info['src_bytes']} bytes)")
        print(f"  dst      {info['dst']}  ({info['dst_bytes']} bytes)")
        print(f"  src sha256 (post-backup):  {info['src_sha256'][:16]}…")
        print(f"  dst sha256:                {info['dst_sha256'][:16]}…")
        return 0

    return _cmd_apply(args)


def _cmd_apply(args: argparse.Namespace) -> int:
    db = Path(args.db).resolve()
    try:
        db.relative_to(LIVE_DATA_DIR)
        live = True
    except ValueError:
        live = False
    if live and not args.allow_live_path:
        print(
            f"refusing: {db} is inside the live data dir {LIVE_DATA_DIR}. "
            "Run against a snapshot copy, or pass --allow-live-path when the operator opens the write phase.",
            file=sys.stderr,
        )
        return 2

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        report, _failures = _reb.reconcile(conn)
        plan = _reb._build_write_plan(report)
        if not args.write:
            print("DRY RUN — pass --write to apply on this database")
            _reb._print_write_plan(plan)
            if args.json:
                print(json.dumps({"plan": plan}, indent=2, sort_keys=True, default=str))
            return 0 if not plan["abort"] else 1
        return _apply_and_verify(conn, report, plan, args)
    finally:
        conn.close()


def _apply_and_verify(conn, report, plan, args) -> int:
    before = dict(plan_counts(plan))
    written = apply_plan(conn, report, plan)
    print("apply committed:")
    _print_apply_summary(written)

    report2, _ = _reb.reconcile(conn)
    plan2 = _reb._build_write_plan(report2)
    after = dict(plan_counts(plan2))
    print("proof re-run on the written copy:")
    print(f"  before: {before}")
    print(f"  after:  {after}")
    if plan2["insert"] or plan2["update"]:
        print("  residual plan items after apply — manual review:", file=sys.stderr)
        _reb._print_write_plan(plan2)
        return 1
    print("  remaining plan is empty of writes; orphans live in escrow_orphan.")
    if args.json:
        print(json.dumps({"before": plan, "after": plan2, "written": written}, indent=2, sort_keys=True, default=str))
    return 0


def plan_counts(plan: dict[str, Any]) -> dict[str, int]:
    return {
        "abort": len(plan["abort"]),
        "anomalies": len(plan["anomalies"]),
        "insert": len(plan["insert"]),
        "update": len(plan["update"]),
        "manual_review": len(plan["manual_review"]),
        "report_only": len(plan["report_only"]),
        "unchanged": plan["unchanged"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
