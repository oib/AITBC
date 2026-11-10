#!/usr/bin/env python3
"""Operator commands for the bridge deposit ledger.

    python -m bridge_monitor.admin <command> [--env-file PATH]

(or `scripts/ops/bridge-admin.sh <command>`, which sets PYTHONPATH itself)

Commands:
    status <tx_hash>                 show the ledger row
    list [--status S] [--limit N]    recent ledger rows, newest first
                                     (e.g. --status funding shows FUNDING
                                     rows — otherwise journal-only)
    write-off <tx_hash> --reason STR terminal write-off; the reason is
                                     required and lands in error_message
    abandon-and-resign <tx_hash>     abandon a stuck SUBMITTED payout —
                                     refuses unless the payout account's
                                     on-chain nonce has passed the
                                     envelope's nonce AND the envelope's
                                     hash is not sealed on chain. The row
                                     then goes to PENDING_RETRY and a
                                     fresh payout is built ledger-first.
    manual-payout <to> <amount_ait>  send a manual payout through the same
                                     ledger-first path as monitor payouts
                                     (synthetic row, SUBMITTED, sweep
                                     owns sealing). This is the ONLY
                                     permitted way to send from the
                                     payout account outside the monitor.

The payout account's nonce must only ever move through ledger rows —
an ad-hoc send can occupy the nonce a stored envelope holds, leaving
the deposit permanently stuck (or worse, double-paying later).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal


def _load_env_file(path: str) -> None:
    """Populate os.environ from an EnvironmentFile-style env file."""
    try:
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)
    except OSError as e:
        print(f"warning: cannot read env file {path}: {e}", file=sys.stderr)


def _valid_recipient(addr: object) -> bool:
    """True when the row carries a syntactically valid AIT recipient."""
    from .storage import valid_ait_recipient

    return valid_ait_recipient(addr)


def _admin_lock() -> int | None:
    """Exclusive non-blocking flock serializing mutating admin commands.

    Two concurrent invocations race check-then-act: both ``manual-payout``
    runs would pass ``_payout_in_flight()`` before either writes its
    SUBMITTED row, then sign envelopes on the same nonce — the exact
    mempool collision the one-envelope rule exists to prevent. The lock
    file sits next to the ledger DB so ``BRIDGE_DEPOSITS_DB``/``DATA_DIR``
    overrides relocate it into the scratch tree too. The monitor sweep
    takes the same lock around its own payout decision+submit, so a
    manual command and a sweep pass cannot interleave either. Returns
    the lock fd (close to release) or None when another holder has it.
    """
    from .storage import try_admin_lock

    return try_admin_lock()


def write_off_denial_reason(d: dict, allow_recipient: bool) -> str | None:
    """None when the row may be written off, else why not."""
    if _valid_recipient(d.get("ait_recipient")) and not allow_recipient:
        return (
            f"has a valid recipient {d.get('ait_recipient')} — that is money owed, "
            "not a lost deposit (use --unpaid-with-recipient to override deliberately)"
        )
    if d.get("status") == "completed" and d.get("ait_tx_hash"):
        # A completed row WITH a payout hash may have actually paid — a
        # completed row with NO hash is a phantom: recorded, nothing sent.
        return "is COMPLETED with a payout hash — cannot write off a paid deposit"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(prog="bridge_monitor.admin")
    parser.add_argument("command", choices=["status", "list", "write-off", "abandon-and-resign", "manual-payout"])
    parser.add_argument("args", nargs="*", help="command arguments")
    parser.add_argument("--reason", default=None, help="required for write-off")
    parser.add_argument("--status", default=None, help="list: filter to this row status (e.g. funding, failed)")
    parser.add_argument("--limit", type=int, default=50, help="list: max rows (default 50)")
    parser.add_argument(
        "--unpaid-with-recipient",
        action="store_true",
        help="permit writing off a deposit that has a valid recipient — owed money, not a lost deposit",
    )
    parser.add_argument(
        "--env-file",
        default=os.getenv("BRIDGE_MONITOR_ENV", "/etc/aitbc/aitbc-bridge-monitor.env"),
        help="env file with BRIDGE_*/GENESIS_* vars (default: monitor's own)",
    )
    ns = parser.parse_args()
    _load_env_file(ns.env_file)

    # Storage path comes from DATA_DIR like the service; allow override so
    # an operator can point at a copied DB for inspection. init_db() runs
    # the additive migrations so a ledger older than the code still reads.
    from .main import BridgeMonitor
    from .storage import BridgeDepositStatus, create_deposit, get_deposit, get_deposits, init_db, update_deposit

    init_db()

    def cmd_list(status: str | None, limit: int) -> int:
        # A negative LIMIT is unlimited in SQLite — clamp so --limit -1
        # cannot dump the whole ledger.
        limit = max(1, limit)
        filt = None
        if status is not None:
            try:
                filt = BridgeDepositStatus(status.lower())
            except ValueError:
                print(f"unknown status {status!r} — one of: {', '.join(s.value for s in BridgeDepositStatus)}")
                return 2
        rows = get_deposits(status=filt, limit=limit)
        for d in rows:
            print(
                f"{d.get('created_at', '')}  {d.get('status', ''):<15} "
                f"{d.get('eth_tx_hash', '')}  {d.get('eth_from_address', '')}  "
                f"{d.get('eth_amount', '')} ETH" + (f"  err={d['error_message']}" if d.get("error_message") else "")
            )
        if not rows:
            print("no rows" + (f" with status {filt.value}" if filt else ""))
        return 0

    def cmd_status(tx_hash: str) -> int:
        d = get_deposit(tx_hash)
        if not d:
            print(f"no deposit row {tx_hash}")
            return 1
        for k, v in d.items():
            if k == "signed_tx":
                v = f"<{len(v)} chars>" if v else v
            print(f"{k}: {v}")
        return 0

    def cmd_write_off(tx_hash: str, reason: str | None, allow_recipient: bool = False) -> int:
        if not reason or not reason.strip():
            print("write-off requires --reason (a written justification is mandatory)")
            return 2
        d = get_deposit(tx_hash)
        if not d:
            print(f"no deposit row {tx_hash}")
            return 1
        denial = write_off_denial_reason(d, allow_recipient)
        if denial:
            print(f"deposit {tx_hash} {denial}")
            return 1
        update_deposit(tx_hash, status=BridgeDepositStatus.WRITTEN_OFF, error_message=reason.strip())
        print(f"deposit {tx_hash} written off: {reason.strip()}")
        return 0

    def cmd_abandon(tx_hash: str) -> int:
        ok, msg = BridgeMonitor().abandon_payout(tx_hash)
        print(msg)
        return 0 if ok else 1

    def _report(msg: str, code: int) -> int:
        print(msg)
        return code

    def cmd_manual_payout(to: str, amount: str) -> int:
        try:
            ait_amount = Decimal(amount)
        except ArithmeticError:
            return _report(f"invalid amount {amount!r}", 2)
        # Decimal('NaN') parses fine but every comparison with it raises
        # InvalidOperation; Decimal('Infinity') passes "> 0" and would sign
        # an infinite payout. Both must die here, before a row exists.
        if not ait_amount.is_finite() or ait_amount <= 0:
            return _report("amount must be a finite number > 0", 2)
        # Same recipient rule as every other payout path — a non-hex
        # 'address' only fails later inside the signer, leaving an orphan
        # row behind.
        if not _valid_recipient(to):
            return _report(f"invalid AIT recipient {to!r}", 2)
        # Serialize like the monitor's own payout paths: the nonce comes
        # from committed chain state, so a second in-flight envelope signs
        # the SAME nonce and the two collide in the mempool — the exact
        # failure _payout_in_flight exists to prevent. Construct the
        # monitor before creating the row so a missing env var cannot
        # leave an orphan PENDING row either.
        mon = BridgeMonitor()
        if mon._payout_in_flight():
            return _report(
                "a payout envelope is already in flight (SUBMITTED) — refusing: "
                "a second envelope would sign the same nonce and collide. "
                "Wait for it to seal or run abandon-and-resign first",
                1,
            )
        tx_hash = f"manual-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%f')}"
        if not create_deposit(tx_hash, "manual", "0", to):
            return _report(f"cannot create manual payout row {tx_hash}", 1)
        if not mon._submit_payout(tx_hash, to, ait_amount):
            # Nothing was broadcast, and no sweep owns a 'manual-*' PENDING
            # row (the retry pass would reprice eth_amount='0' forever) —
            # leave the row terminally FAILED, not in limbo.
            update_deposit(
                tx_hash,
                status=BridgeDepositStatus.FAILED,
                error_message="manual payout: failed to build signed payout",
            )
            return _report(f"manual payout {tx_hash}: failed to build signed payout — row marked FAILED", 1)
        return _report(f"manual payout {tx_hash}: {ait_amount} AIT to {to} submitted — sweep owns sealing", 0)

    # Mutating commands run under the admin lock: the ledger's
    # one-envelope-in-flight invariant is check-then-act, so two concurrent
    # admins could both pass _payout_in_flight() and sign colliding
    # envelopes. Read commands stay lock-free.
    lock_fd = None
    if ns.command in {"write-off", "abandon-and-resign", "manual-payout"}:
        lock_fd = _admin_lock()
        if lock_fd is None:
            print("another bridge-admin mutation is in progress — refusing to run concurrently", file=sys.stderr)
            return 1
    try:
        if ns.command == "status":
            return cmd_status(ns.args[0]) if len(ns.args) == 1 else parser.error("status needs <tx_hash>")
        if ns.command == "list":
            return cmd_list(ns.status, ns.limit)
        if ns.command == "write-off":
            if len(ns.args) != 1:
                parser.error("write-off needs <tx_hash>")
            return cmd_write_off(ns.args[0], ns.reason, ns.unpaid_with_recipient)
        if ns.command == "abandon-and-resign":
            return cmd_abandon(ns.args[0]) if len(ns.args) == 1 else parser.error("abandon-and-resign needs <tx_hash>")
        if ns.command == "manual-payout":
            if len(ns.args) != 2:
                parser.error("manual-payout needs <to> <amount_ait>")
            return cmd_manual_payout(ns.args[0], ns.args[1])
        return 2
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
