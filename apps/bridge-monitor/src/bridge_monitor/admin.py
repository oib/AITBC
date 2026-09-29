#!/usr/bin/env python3
"""Operator commands for the bridge deposit ledger.

    python -m bridge_monitor.admin <command> [--env-file PATH]

Commands:
    status <tx_hash>                 show the ledger row
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="bridge_monitor.admin")
    parser.add_argument("command", choices=["status", "write-off", "abandon-and-resign", "manual-payout"])
    parser.add_argument("args", nargs="*", help="command arguments")
    parser.add_argument("--reason", default=None, help="required for write-off")
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
    from .storage import BridgeDepositStatus, create_deposit, get_deposit, init_db, update_deposit

    init_db()

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

    def cmd_write_off(tx_hash: str, reason: str | None) -> int:
        if not reason or not reason.strip():
            print("write-off requires --reason (a written justification is mandatory)")
            return 2
        d = get_deposit(tx_hash)
        if not d:
            print(f"no deposit row {tx_hash}")
            return 1
        if d.get("status") == BridgeDepositStatus.COMPLETED.value:
            print(f"deposit {tx_hash} is COMPLETED — cannot write off a paid deposit")
            return 1
        update_deposit(tx_hash, status=BridgeDepositStatus.WRITTEN_OFF, error_message=reason.strip())
        print(f"deposit {tx_hash} written off: {reason.strip()}")
        return 0

    def cmd_abandon(tx_hash: str) -> int:
        ok, msg = BridgeMonitor().abandon_payout(tx_hash)
        print(msg)
        return 0 if ok else 1

    def cmd_manual_payout(to: str, amount: str) -> int:
        try:
            ait_amount = Decimal(amount)
        except Exception:
            print(f"invalid amount {amount!r}")
            return 2
        if ait_amount <= 0:
            print("amount must be > 0")
            return 2
        if not (to.startswith("0x") and len(to) == 42):
            print(f"invalid AIT recipient {to!r}")
            return 2
        tx_hash = f"manual-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%f')}"
        if not create_deposit(tx_hash, "manual", "0", to):
            print(f"cannot create manual payout row {tx_hash}")
            return 1
        mon = BridgeMonitor()
        if not mon._submit_payout(tx_hash, to, ait_amount):
            print(f"manual payout {tx_hash}: failed to build signed payout — row is PENDING_RETRY-able")
            return 1
        print(f"manual payout {tx_hash}: {ait_amount} AIT to {to} submitted — sweep owns sealing")
        return 0

    if ns.command == "status":
        return cmd_status(ns.args[0]) if ns.args else parser.error("status needs <tx_hash>")
    if ns.command == "write-off":
        return cmd_write_off(ns.args[0], ns.reason) if ns.args else parser.error("write-off needs <tx_hash>")
    if ns.command == "abandon-and-resign":
        return cmd_abandon(ns.args[0]) if ns.args else parser.error("abandon-and-resign needs <tx_hash>")
    if ns.command == "manual-payout":
        if len(ns.args) < 2:
            parser.error("manual-payout needs <to> <amount_ait>")
        return cmd_manual_payout(ns.args[0], ns.args[1])
    return 2


if __name__ == "__main__":
    sys.exit(main())
