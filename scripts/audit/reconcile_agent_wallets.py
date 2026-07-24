#!/usr/bin/env python3
"""Reconcile agent wallet budgets against expected balances.

ponytail: This script works with the shared `aitbc.agent_economics.Budget`
type. A future version will load live wallet and escrow balances from the
blockchain node; for v0.12.0 it accepts a JSON file of expected balances and
reports any budget whose `available` total does not match.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from aitbc.agent_economics import Budget


def load_expected_balances(path: Path) -> dict[str, str]:
    """Load a mapping of budget_id -> expected total balance."""
    data = json.loads(path.read_text())
    return {str(k): str(v) for k, v in data.items()}


def reconcile(
    budgets: list[Budget],
    expected: dict[str, str],
) -> tuple[bool, list[str]]:
    """Compare each budget's total to the expected balance.

    Returns (ok, messages).
    """
    messages: list[str] = []
    ok = True
    budget_ids = {b.budget_id for b in budgets}
    for budget_id in expected:
        if budget_id not in budget_ids:
            ok = False
            messages.append(f"missing budget {budget_id}")

    for budget in budgets:
        expected_total = Decimal(expected.get(budget.budget_id, "0"))
        if budget.total != expected_total:
            ok = False
            messages.append(f"budget {budget.budget_id}: expected {expected_total}, got {budget.total}")
    return ok, messages


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Reconcile agent wallet budgets")
    parser.add_argument(
        "--expected",
        type=Path,
        required=True,
        help="JSON file with budget_id -> expected total balance",
    )
    parser.add_argument(
        "--budgets",
        type=Path,
        help="JSON file with a list of budget objects (optional; demo mode uses a sample)",
    )
    args = parser.parse_args(argv)

    expected = load_expected_balances(args.expected)

    if args.budgets:
        raw = json.loads(args.budgets.read_text())
        budgets = [Budget(**item) for item in raw]
    else:
        # Demo mode: one sample budget.
        budgets = [
            Budget(
                budget_id="agent-1",
                agent_id="agent-1",
                chain_id="ait-hub",
                token="AITBC",
                total=Decimal("100"),
            )
        ]

    ok, messages = reconcile(budgets, expected)
    for msg in messages:
        print(msg)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
