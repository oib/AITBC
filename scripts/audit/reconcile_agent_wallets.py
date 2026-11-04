#!/usr/bin/env python3
"""Reconcile agent wallet budgets against expected balances.

ponytail: This script can reconcile against a local JSON file of budgets or
fetch live balances from a wallet daemon RPC. The default RPC endpoint
template is a guess; pass `--endpoint-template` to match your daemon's API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import URLError

from aitbc.agent_economics import Budget


_DEFAULT_RPC_TEMPLATE = "/wallet/{budget_id}/balance"


def _to_decimal(value: str | int | float | None) -> Decimal:
    """Convert a JSON value to Decimal."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _load_expected_balances(path: Path) -> dict[str, str]:
    """Load a mapping of budget_id -> expected total balance."""
    data = json.loads(path.read_text())
    out = {}
    for k, v in data.items():
        try:
            Decimal(str(v))
        except InvalidOperation:
            raise SystemExit(f"expected balance for {k!r} is not a number: {v!r}") from None
        out[str(k)] = str(v)
    return out


def _load_budgets(path: Path) -> list[Budget]:
    """Load a list of Budget objects from a JSON file."""
    raw = json.loads(path.read_text())
    budgets = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        budgets.append(
            Budget(
                budget_id=str(item["budget_id"]),
                agent_id=str(item.get("agent_id", "")),
                chain_id=str(item.get("chain_id", "ait-hub")),
                token=str(item.get("token", "AITBC")),
                total=_to_decimal(item.get("total")),
                allocated=_to_decimal(item.get("allocated")),
                meta=item.get("meta", {}),
            )
        )
    return budgets


def _fetch_live_balance(
    budget_id: str,
    rpc_url: str,
    endpoint_template: str,
    api_key: str | None = None,
) -> Decimal | None:
    """Fetch a live balance from a wallet daemon RPC."""
    path = endpoint_template.format(budget_id=budget_id)
    url = f"{rpc_url.rstrip('/')}{path}"
    # `rpc_url` arrives from --wallet-rpc-url or $WALLET_RPC_URL, and urlopen honours every
    # scheme it knows, `file:` among them. A typo or a stale environment would otherwise read
    # a local path and, worse, hand it the bearer token below.
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"wallet RPC URL must be http or https, got: {url!r}")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers)  # type: ignore[arg-type]
    try:
        # the scheme is checked against http/https above. B310 is a blacklist
        # nosec B310
        # rule on the call itself and fires whatever guards precede it.
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            payload = json.loads(resp.read().decode())
    except (URLError, json.JSONDecodeError, TimeoutError):
        return None

    # Accept a few common response shapes.
    for key in ("balance", "total", "available", "amount"):
        if key in payload:
            return _to_decimal(payload[key])
    return None


def reconcile(
    budgets: list[Budget],
    expected: dict[str, str],
    *,
    rpc_url: str | None = None,
    endpoint_template: str = _DEFAULT_RPC_TEMPLATE,
    api_key: str | None = None,
) -> tuple[bool, list[str]]:
    """Compare each budget's total to the expected balance.

    If ``rpc_url`` is set, live balances are fetched and compared; a failed or
    unreadable fetch is itself a mismatch — silently falling back to the
    recorded total made the check pass whenever the daemon was down.
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
        actual = budget.total
        if rpc_url:
            live = _fetch_live_balance(budget.budget_id, rpc_url, endpoint_template, api_key)
            if live is None:
                ok = False
                messages.append(f"budget {budget.budget_id}: live balance unreadable")
                continue
            actual = live
        if actual != expected_total:
            ok = False
            messages.append(f"budget {budget.budget_id}: expected {expected_total}, got {actual}")
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
        required=True,
        help="JSON file with a list of budget objects",
    )
    parser.add_argument(
        "--wallet-rpc-url",
        default=os.getenv("WALLET_RPC_URL", ""),
        help="Optional wallet daemon RPC URL to fetch live balances",
    )
    parser.add_argument(
        "--endpoint-template",
        default=_DEFAULT_RPC_TEMPLATE,
        help="URL path template for fetching a balance ({budget_id})",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("WALLET_API_KEY", ""),
        help="API key for the wallet daemon RPC",
    )
    args = parser.parse_args(argv)

    expected = _load_expected_balances(args.expected)

    budgets = _load_budgets(args.budgets)

    ok, messages = reconcile(
        budgets,
        expected,
        rpc_url=args.wallet_rpc_url or None,
        endpoint_template=args.endpoint_template,
        api_key=args.api_key or None,
    )
    for msg in messages:
        print(msg)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
