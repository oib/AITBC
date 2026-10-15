#!/usr/bin/env python3
"""Operator commands for escrowed AIT->ETH sell locks (ETH-13).

Run on hub inside the wallet environment — the same env files the
aitbc-wallet unit loads::

    cd /opt/aitbc
    PYTHONPATH=/opt/aitbc/apps/wallet/src:/opt/aitbc/packages/py/aitbc-sdk/src:/opt/aitbc/packages/py/aitbc-crypto/src \
        venv/bin/python -m wallet_app.bridge.sell_admin <command> [args]

Commands:
    status                                sell lane enablement + non-secret config
                                          (sell_config_status + flags + limits;
                                          env-only — runs before the ledger gate)
    list [--status S]...                  sell-lock rows (default: every open status)
    inspect <ait_tx_hash>                 full row + quote + persisted sweep intent
                                          (never the signed blob) + escrow account view
    confirm-swept <ait_tx_hash> --tx H    resolve a 'needs_review_sweep' row whose
                                          outflow DID seal: H is re-verified on-chain
                                          with the monitor's own match rule (nonce +
                                          recipient + amount + payload.sell_ref) before
                                          the row goes 'settled'/'refunded'
    requeue <ait_tx_hash>                 return a 'needs_review_sweep' row to the lane
                                          its intent was in ('released' for a settle,
                                          'refund_pending' for a refund) — the monitor
                                          re-runs its normal sweep path next poll
    write-off <ait_tx_hash> --reason …    terminal abandon; the ETH leg stays recorded,
                                          the AIT leg is marked abandoned
    sweep-now <ait_tx_hash>               queued_fee_settle/queued_fee_refund only: run
                                          the monitor's own _escrow_sweep once now — an
                                          accelerator for "I just funded the escrow",
                                          not an override (a short float re-parks)

Safety rules (ETH-13):
- Root on the hub host only: the command refuses when euid != 0 and when
  BLOCKCHAIN_MODE != 'hub' in the loaded env set — the check is env-derived,
  no hostname is hardcoded. It also refuses when the ledger DB does not
  exist rather than let init_db create an empty one elsewhere.
- 'needs_review_sweep' is the only operator-gated status: confirm-swept and
  requeue refuse any other row, and plain 'needs_review' (the ETH-release
  path) is never matched — the monitor still auto-resumes it.
- Every status change goes through bridge_db.update_sell_lock_status — the
  same write path the monitor uses. Nothing here writes raw SQL.
- Nothing here signs or broadcasts except 'sweep-now', which runs the
  monitor's own _escrow_sweep — the one place nonce+blob are persisted
  before broadcast. 'requeue' only returns the row to the monitor; the
  monitor signs. 'confirm-swept' verifies, it never sends.
- Serialization holds: 'requeue' and 'sweep-now' refuse while a
  'settling'/'refunding' row is in flight — the one-sweep rule applies to
  manual actions too.
- write-off refuses rows with a live send in flight ('releasing',
  'settling', 'refunding') — those are machine-owned until resolved.
- Every mutating verb is a dry-run by default; --confirm requires a
  non-empty --note. Resolutions stamp resolved_by/resolved_at/operator_note
  and carry 'operator:<verb>' in the row's error field (confirm-swept,
  requeue, write-off).
- SELL_ESCROW_ENABLED is not required: operator duties exist even while
  the feature flag is dark. What is required for chain-touching verbs is
  the sell config (AIT_SELL_ESCROW / SELL_TREASURY_ADDRESS / CHAIN_ID) and,
  for sweep-now, a loadable escrow key slot.
- Output never prints the stored signed blob, key material, or an RPC URL
  with path/query — endpoint text is redacted to scheme://host.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Any

from .url_redact import redact_text
from .withdraw_admin import _DEFAULT_ENV_FILES, _load_env_files, _sync_wdm_env

# The only status an operator action may move. Plain 'needs_review' (the
# ETH-release path) stays machine-owned — it still auto-resumes.
_OPERATOR_GATED_STATUS = "needs_review_sweep"

# Fee-parked rows sweep-now may accelerate.
_FEE_QUEUED_STATUSES = ("queued_fee_settle", "queued_fee_refund")

# Rows with a live send in flight are machine-owned: a release blob or a
# sweep blob may still seal — abandoning the row under it strands the
# ledger truth. write-off refuses these.
_IN_FLIGHT_STATUSES = ("releasing", "settling", "refunding")

# Literal requeue targets (decided 14 Oct): the row returns to the lane it
# was in and the monitor's normal path runs — no quote/cap re-check.
_LANE_REQUEUE_TARGET = {"settle": "released", "refund": "refund_pending"}
_LANE_FINAL_STATUS = {"settle": "settled", "refund": "refunded"}
_LANE_HASH_FIELD = {"settle": "settle_tx_hash", "refund": "refund_tx_hash"}


def _intent_metadata(row: dict[str, Any]) -> dict[str, Any] | None:
    """Log-safe view of the persisted sweep intent — parsed fields only,
    never the signed blob or its signature."""
    raw = row.get("escrow_out_tx")
    if not raw:
        return None
    try:
        tx = json.loads(str(raw))
    except Exception:
        return {"unparseable": True}
    if not isinstance(tx, dict):
        return {"unparseable": True}
    return {
        "to": tx.get("to"),
        "amount": tx.get("amount"),
        "fee": tx.get("fee"),
        "nonce": tx.get("nonce"),
        "payload": tx.get("payload"),
        "signature": "<present>" if tx.get("signature") else None,
    }


def _sweep_lane(row: dict[str, Any], treasury_address: str | None) -> str | None:
    """Which lane the row's persisted sweep intent was in — 'settle' or
    'refund', or None when the intent blob is missing/unreadable.

    The lane cannot be read from the row's status: by the time an operator
    touches it the status is 'needs_review_sweep' either way. The stored
    blob's payload.reason is authoritative ('sell_settle' vs the refund
    reason); the recipient address is the fallback check.
    """
    meta = _intent_metadata(row)
    if not meta or meta.get("unparseable"):
        return None
    payload = meta.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    reason = payload.get("reason")
    if reason == "sell_settle":
        return "settle"
    if reason:
        return "refund"
    to = str(meta.get("to") or "").lower()
    if treasury_address and to == treasury_address.lower():
        return "settle"
    if to and to == str(row.get("shop_ait_address") or "").lower():
        return "refund"
    return None


def _print_lock(row: dict[str, Any]) -> None:
    for key, val in row.items():
        if key == "escrow_out_tx":
            continue
        print(f"  {key}: {val}")
    blob = row.get("escrow_out_tx")
    print(f"  escrow_out_tx: {'<signed blob withheld>' if blob else None}")
    meta = _intent_metadata(row)
    if meta:
        print("  sweep intent (parsed):")
        for key, val in meta.items():
            print(f"    {key}: {val}")


def _host_gates() -> int:
    """Root on the hub host only (decided 14 Oct): the command exists to
    operate on hub's live ledger — env files and /var/lib/aitbc are
    root-owned there, and only hub carries the bridge monitor. The hub
    check reads BLOCKCHAIN_MODE from the loaded env set, so no hostname is
    baked in."""
    if os.geteuid() != 0:
        print("refusing: sell_admin must run as root — the ledger and env files are root-owned")
        return 2
    if os.environ.get("BLOCKCHAIN_MODE") != "hub":
        print("refusing: sell_admin runs on the hub only (BLOCKCHAIN_MODE=hub in the loaded env set)")
        return 2
    return 0


def _audit_fields(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "resolved_by": args.operator or getpass.getuser(),
        "resolved_at": datetime.now().isoformat(),
        "operator_note": args.note.strip(),
    }


def _require_note(args: argparse.Namespace) -> str | None:
    note = (args.note or "").strip()
    if not note:
        print("refusing: --confirm requires --note (a written justification is mandatory)")
        return None
    return note


def _inflight_refusal(db: Any) -> dict[str, Any] | None:
    """The in-flight sweep blocking a manual action, or None."""
    other: dict[str, Any] | None = db.get_sell_inflight_sweep()
    if other:
        print(
            f"refusing: sweep already in flight ({other['ait_tx_hash']} status={other['status']}) "
            "— sweep serialization holds across manual actions"
        )
    return other


def _load_sell_config(sellmon: Any) -> Any | None:
    """The sell config for chain-touching verbs; refusal printed on failure."""
    try:
        return sellmon._sell_config()
    except ValueError as e:
        print(f"refusing: sell escrow config unusable: {e}")
        return None


def _review_row_or_refuse(db: Any, ait_tx_hash: str) -> dict[str, Any] | None:
    """The row gate shared by confirm-swept and requeue: exists, and is in
    the one operator-gated status. Prints the refusal and returns None."""
    row: dict[str, Any] | None = db.get_sell_lock_by_ait_tx_hash(ait_tx_hash)
    if not row:
        print(f"no sell lock {ait_tx_hash}")
        return None
    _print_lock(row)
    if row["status"] != _OPERATOR_GATED_STATUS:
        print(f"refusing: status={row['status']} is not operator-gated (only {_OPERATOR_GATED_STATUS} resolves here)")
        return None
    return row


async def _match_sealed_outflow(sellmon: Any, cfg: Any, row: dict[str, Any], nonce: int) -> tuple[str, dict[str, Any]] | None:
    """(lane, outflow) for the row's recorded nonce — the monitor's own
    match rule (nonce + recipient + amount + payload.sell_ref). When the
    intent blob is unreadable the sealed outflow's recipient decides the
    lane; both probes still enforce the full rule."""
    lane = _sweep_lane(row, cfg.treasury_address)
    for probe in [lane] if lane else ["settle", "refund"]:
        to_address, amount_units, sell_ref = sellmon._expected_sweep(cfg, row, probe)
        outflow = await sellmon._find_escrow_outflow(cfg, int(nonce), to_address, amount_units, sell_ref)
        if outflow is not None:
            return probe, outflow
    return None


async def _cmd_list(db: Any, args: argparse.Namespace) -> int:
    statuses = tuple(args.status) if args.status else tuple(db._SELL_OPEN_STATUSES)
    rows = db.get_sell_locks_by_status(statuses)
    if not rows:
        print("no sell locks match")
        return 0
    for r in rows:
        print(f"{r['id']}  {r['status']}  {r['amount_ait']} AIT  shop={r['shop_ait_address']}  lock={r['ait_tx_hash']}")
        if r.get("error"):
            print(f"    error: {r['error']}")
    print(f"{len(rows)} row(s)")
    return 0


async def _cmd_inspect(db: Any, sellmon: Any, ait_tx_hash: str) -> int:
    row = db.get_sell_lock_by_ait_tx_hash(ait_tx_hash)
    if not row:
        print(f"no sell lock {ait_tx_hash}")
        return 1
    _print_lock(row)
    if row.get("quote_id"):
        quote = db.get_sell_quote(str(row["quote_id"]))
        if quote:
            print("quote:")
            for key, val in quote.items():
                print(f"  {key}: {val}")
    cfg = _load_sell_config(sellmon)
    if cfg is None:
        return 0
    lane = _sweep_lane(row, cfg.treasury_address)
    if lane:
        print(f"  sweep lane: {lane}")
    try:
        nonce, balance = await sellmon._account_view(cfg.escrow_address)
        print(f"escrow chain view: address={cfg.escrow_address} nonce={nonce} balance={balance} AIT")
    except Exception as e:
        print(f"escrow chain view unavailable: {redact_text(str(e))}")
    return 0


async def _cmd_confirm_swept(db: Any, sellmon: Any, args: argparse.Namespace) -> int:
    ait_tx_hash = args.ait_tx_hash
    row = _review_row_or_refuse(db, ait_tx_hash)
    if row is None:
        return 1
    nonce = row.get("escrow_out_nonce")
    if nonce is None:
        print("refusing: no recorded sweep nonce — the match rule cannot run; use write-off")
        return 1
    cfg = _load_sell_config(sellmon)
    if cfg is None:
        return 1

    matched = await _match_sealed_outflow(sellmon, cfg, row, nonce)
    if matched is None:
        print(
            f"refusing: no sealed escrow outflow at nonce {nonce} matches this row's intent "
            "(recipient + amount + payload.sell_ref all required)"
        )
        return 1
    lane, outflow = matched
    sealed_hash = str(outflow.get("tx_hash") or outflow.get("hash") or "")
    if sealed_hash.lower() != str(args.tx).lower():
        print(f"refusing: supplied hash {args.tx} does not equal the sealed outflow {sealed_hash} found by the match rule")
        return 1

    final_status = _LANE_FINAL_STATUS[lane]
    hash_field = _LANE_HASH_FIELD[lane]
    print(f"verification: sealed {lane} outflow {sealed_hash} at escrow nonce {nonce} — matches intent")
    print(f"planned write: status={final_status} {hash_field}={sealed_hash}")
    if not args.confirm:
        print("dry-run: no write. Re-run with --confirm --note '…' to resolve.")
        return 0
    note = _require_note(args)
    if note is None:
        return 2
    ok = db.update_sell_lock_status(
        ait_tx_hash,
        final_status,
        **{hash_field: sealed_hash},
        error=f"operator:confirm-swept {note}",
        **_audit_fields(args),
    )
    if not ok:
        print("refusing: ledger write touched no row")
        return 1
    print(f"row → {final_status} ({hash_field}={sealed_hash})")
    return 0


async def _cmd_requeue(db: Any, sellmon: Any, args: argparse.Namespace) -> int:
    ait_tx_hash = args.ait_tx_hash
    row = _review_row_or_refuse(db, ait_tx_hash)
    if row is None:
        return 1

    treasury = None
    cfg = _load_sell_config(sellmon)
    if cfg is not None:
        treasury = cfg.treasury_address
    lane = _sweep_lane(row, treasury)
    if lane is None:
        print(
            "refusing: sweep intent blob missing/unreadable — cannot tell which lane the row was in "
            "(settle→released, refund→refund_pending). Use write-off, or restore the intent and retry."
        )
        return 1
    if _inflight_refusal(db) is not None:
        return 1

    target = _LANE_REQUEUE_TARGET[lane]
    print(f"planned write: status={target} ({lane} lane) — the monitor's next poll re-runs the sweep path")
    if not args.confirm:
        print("dry-run: no write. Re-run with --confirm --note '…' to requeue.")
        return 0
    note = _require_note(args)
    if note is None:
        return 2
    ok = db.update_sell_lock_status(
        ait_tx_hash,
        target,
        error=f"operator:requeue {note}",
        **_audit_fields(args),
    )
    if not ok:
        print("refusing: ledger write touched no row")
        return 1
    print(f"row → {target}; the monitor re-sweeps at a fresh nonce on its next poll")
    return 0


async def _cmd_write_off(db: Any, args: argparse.Namespace) -> int:
    ait_tx_hash = args.ait_tx_hash
    row = db.get_sell_lock_by_ait_tx_hash(ait_tx_hash)
    if not row:
        print(f"no sell lock {ait_tx_hash}")
        return 1
    _print_lock(row)
    if row["status"] not in db._SELL_OPEN_STATUSES:
        print(f"refusing: status={row['status']} is already terminal")
        return 1
    if row["status"] in _IN_FLIGHT_STATUSES:
        print(
            f"refusing: status={row['status']} has a live send in flight — "
            "resolve it first (confirm-swept / requeue / let the monitor decide)"
        )
        return 1

    print(f"planned write: status=written_off reason={args.reason}")
    if row.get("eth_tx_hash") or row.get("released_at"):
        print("note: the ETH leg already left — the write-off records the AIT leg as abandoned")
    if not args.confirm:
        print("dry-run: no write. Re-run with --confirm --note '…' to write off.")
        return 0
    note = _require_note(args)
    if note is None:
        return 2
    ok = db.update_sell_lock_status(
        ait_tx_hash,
        "written_off",
        error=f"operator:write-off {args.reason}",
        **_audit_fields(args),
    )
    if not ok:
        print("refusing: ledger write touched no row")
        return 1
    print("row → written_off (terminal; the monitor will never touch it again)")
    return 0


def _sweep_plan(sellmon: Any, cfg: Any, row: dict[str, Any]) -> tuple[str, str, str, str, Decimal]:
    """(to_address, reason, intent_status, fee_park_status, required) for a
    queued_fee_* row — the same values the monitor's own wrappers pass."""
    lane = "settle" if row["status"] == "queued_fee_settle" else "refund"
    to_address, _units, _ref = sellmon._expected_sweep(cfg, row, lane)
    reason = "sell_settle" if lane == "settle" else sellmon._parked_refund_reason(row)
    intent_status = "settling" if lane == "settle" else "refunding"
    required = Decimal(str(row["amount_ait"])) + sellmon._sweep_fee_ait()
    return to_address, reason, intent_status, str(row["status"]), required


async def _cmd_sweep_now(db: Any, sellmon: Any, args: argparse.Namespace) -> int:
    ait_tx_hash = args.ait_tx_hash
    row = db.get_sell_lock_by_ait_tx_hash(ait_tx_hash)
    if not row:
        print(f"no sell lock {ait_tx_hash}")
        return 1
    _print_lock(row)
    if row["status"] not in _FEE_QUEUED_STATUSES:
        print(f"refusing: status={row['status']} — sweep-now only accelerates {list(_FEE_QUEUED_STATUSES)}")
        return 1
    if _inflight_refusal(db) is not None:
        return 1
    cfg = _load_sell_config(sellmon)
    if cfg is None:
        return 1
    key_error = sellmon._validate_escrow_key(cfg)
    if key_error:
        print(f"refusing: {key_error} — a manual sweep can only sign where the escrow key is configured")
        return 1

    to_address, reason, intent_status, fee_park_status, required = _sweep_plan(sellmon, cfg, row)
    print(f"planned sweep: {row['amount_ait']} AIT -> {to_address} (reason={reason}), float needed {required} AIT")
    try:
        _nonce, balance = await sellmon._account_view(cfg.escrow_address)
        print(f"escrow balance: {balance} AIT ({'sufficient' if balance >= required else 'SHORT — would re-park'})")
    except Exception as e:
        print(f"escrow balance unreadable: {redact_text(str(e))}")
    if not args.confirm:
        print("dry-run: no write, no send. Re-run with --confirm --note '…' to sweep now.")
        return 0
    note = _require_note(args)
    if note is None:
        return 2

    # Audit the operator action first; the sweep's own status write then
    # carries the lane change (its error write re-parks or persists intent).
    db.update_sell_lock_status(ait_tx_hash, row["status"], **_audit_fields(args))

    outcome = await sellmon._escrow_sweep(cfg, row, to_address, reason, intent_status, fee_park_status)
    return _sweep_outcome_rc(outcome, intent_status, fee_park_status)


def _sweep_outcome_rc(outcome: str, intent_status: str, fee_park_status: str) -> int:
    if outcome == "sent":
        print(f"sweep broadcast — row is '{intent_status}' until the outflow seals")
        return 0
    if outcome == "fee_parked":
        print(f"sweep re-parked — escrow float still short (see {fee_park_status} row error)")
        return 1
    if outcome == "deferred":
        print("sweep deferred — another sweep entered flight between checks; nothing sent")
        return 1
    print(f"unexpected sweep outcome {outcome!r}")
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sell_admin",
        description="Operator commands for escrowed AIT->ETH sell locks (see module docstring).",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=None,
        help="EnvironmentFile to load (repeatable; default: the aitbc-wallet unit's set)",
    )
    parser.add_argument("--db", default=None, help="bridge sqlite path (default: the service's DB_PATH)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="sell lane enablement + non-secret config (read-only)")

    p_list = sub.add_parser("list", help="list sell locks (default: all open statuses)")
    p_list.add_argument("--status", action="append", default=None, help="status filter (repeatable)")

    p_inspect = sub.add_parser("inspect", help="full row + quote + intent metadata + escrow chain view")
    p_inspect.add_argument("ait_tx_hash")

    p_confirm = sub.add_parser(
        "confirm-swept", help="resolve needs_review_sweep after re-verifying the sealed outflow (dry-run default)"
    )
    p_confirm.add_argument("ait_tx_hash")
    p_confirm.add_argument("--tx", required=True, help="the sealed escrow outflow tx hash — verified on-chain")
    p_confirm.add_argument("--note", default=None, help="written justification — mandatory with --confirm")
    p_confirm.add_argument("--operator", default=None, help="recorded operator name (default: current user)")
    p_confirm.add_argument("--confirm", action="store_true", help="perform the status write")

    p_requeue = sub.add_parser("requeue", help="return a needs_review_sweep row to its sweep lane (dry-run default)")
    p_requeue.add_argument("ait_tx_hash")
    p_requeue.add_argument("--note", default=None, help="written justification — mandatory with --confirm")
    p_requeue.add_argument("--operator", default=None, help="recorded operator name (default: current user)")
    p_requeue.add_argument("--confirm", action="store_true", help="perform the status write")

    p_off = sub.add_parser("write-off", help="terminal abandon of a sell lock (dry-run default)")
    p_off.add_argument("ait_tx_hash")
    p_off.add_argument("--reason", required=True, help="abandon reason — recorded in the row's error field")
    p_off.add_argument("--note", default=None, help="written justification — mandatory with --confirm")
    p_off.add_argument("--operator", default=None, help="recorded operator name (default: current user)")
    p_off.add_argument("--confirm", action="store_true", help="perform the status write")

    p_sweep = sub.add_parser("sweep-now", help="queued_fee_* only: run the monitor's own _escrow_sweep once (dry-run default)")
    p_sweep.add_argument("ait_tx_hash")
    p_sweep.add_argument("--note", default=None, help="written justification — mandatory with --confirm")
    p_sweep.add_argument("--operator", default=None, help="recorded operator name (default: current user)")
    p_sweep.add_argument("--confirm", action="store_true", help="actually run the sweep attempt")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _load_env_files(args.env_file or _DEFAULT_ENV_FILES)
    if _host_gates():
        return 2

    from . import bridge_db as db
    from . import bridge_withdraw_monitor as wdm
    from . import sell_escrow_monitor as sellmon

    _sync_wdm_env(wdm)
    if args.command == "status":
        # Env-only: the sell lane's config is readable even where no ledger
        # exists yet — exactly the state this verb exists to show.
        print(json.dumps(sellmon.sell_status_document(), indent=2, default=str))
        return 0

    db_target = args.db or db.DB_PATH
    if not os.path.exists(db_target):
        print(f"refusing: no bridge ledger at {db_target} — the command runs where the ledger exists")
        return 2
    if args.db:
        db.DB_PATH = args.db
    db.init_db()

    handlers = {
        "list": lambda: _cmd_list(db, args),
        "inspect": lambda: _cmd_inspect(db, sellmon, args.ait_tx_hash),
        "confirm-swept": lambda: _cmd_confirm_swept(db, sellmon, args),
        "requeue": lambda: _cmd_requeue(db, sellmon, args),
        "write-off": lambda: _cmd_write_off(db, args),
        "sweep-now": lambda: _cmd_sweep_now(db, sellmon, args),
    }
    handler = handlers.get(args.command)
    if handler is None:
        return 2
    return asyncio.run(handler())


if __name__ == "__main__":
    sys.exit(main())
