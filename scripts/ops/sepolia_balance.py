#!/usr/bin/env python3
"""Read-only Sepolia ETH balance and nonce for a list of addresses (ETH-1).

    venv/bin/python scripts/ops/sepolia_balance.py 0xAddr... [0xAddr...]
    venv/bin/python scripts/ops/sepolia_balance.py --rpc-url https://rpc.example 0xAddr...
    venv/bin/python scripts/ops/sepolia_balance.py --json 0xAddr...

Queries a public (or operator-supplied) Ethereum JSON-RPC endpoint with
``eth_getBalance`` and ``eth_getTransactionCount``, both at block tag
``latest`` — the sealed state, not ``pending`` mempool speculation. Print
one line per address or a JSON array with ``--json``.

Guarantees: stdlib only, no private keys touched anywhere, no environment
variables read — the RPC endpoint comes from ``--rpc-url`` or the compiled-in
public default, never from the environment. Exit status is 1 if any address
fails; successful rows are still printed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from decimal import Decimal

WEI_PER_ETH = Decimal(10) ** 18
DEFAULT_RPC_URL = "https://ethereum-sepolia-rpc.publicnode.com"
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class RpcError(RuntimeError):
    """Raised on transport failure or a JSON-RPC error reply."""


def _post_rpc(rpc_url: str, method: str, params: list, timeout: float) -> str:
    """Single JSON-RPC call; returns the raw ``result`` as a string."""
    if not rpc_url.startswith(("http://", "https://")):
        raise RpcError(f"RPC endpoint must be http(s): {rpc_url!r}")
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    request = urllib.request.Request(
        rpc_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # nosec B310 -- http(s)-only endpoint, scheme enforced in _check_url
            payload = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RpcError(f"RPC request failed: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RpcError(f"RPC returned a non-JSON reply: {exc}") from exc
    if "error" in payload:
        raise RpcError(f"RPC error: {payload['error']}")
    result = payload.get("result")
    if not isinstance(result, str):
        raise RpcError(f"RPC reply has no string result: {payload!r}")
    return result


def _hex_quantity(value: str, field: str) -> int:
    """Decode a 0x-prefixed RPC quantity; rejects non-quantity replies."""
    if not value.startswith("0x"):
        raise RpcError(f"{field} is not a 0x quantity: {value!r}")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise RpcError(f"{field} is not a valid hex quantity: {value!r}") from exc


def query_address(rpc_url: str, address: str, timeout: float = 15.0) -> dict:
    """Return ``{"address", "balance_wei", "balance_eth", "nonce"}``.

    ``nonce`` is the confirmed outbound transaction count
    (``eth_getTransactionCount`` at ``latest``).
    """
    if not _ADDRESS_RE.match(address):
        raise ValueError(f"not a 0x + 40-hex address: {address!r}")
    balance_wei = _hex_quantity(
        _post_rpc(rpc_url, "eth_getBalance", [address, "latest"], timeout),
        "balance",
    )
    nonce = _hex_quantity(
        _post_rpc(rpc_url, "eth_getTransactionCount", [address, "latest"], timeout),
        "nonce",
    )
    return {
        "address": address,
        "balance_wei": balance_wei,
        "balance_eth": str(Decimal(balance_wei) / WEI_PER_ETH),
        "nonce": nonce,
    }


def _check_url(rpc_url: str) -> str:
    if not rpc_url.startswith(("http://", "https://")):
        raise SystemExit(f"--rpc-url must be http(s): {rpc_url!r}")
    return rpc_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Sepolia ETH balance and confirmed nonce per address.",
    )
    parser.add_argument("addresses", nargs="+", help="0x-prefixed Ethereum addresses")
    parser.add_argument(
        "--rpc-url",
        default=DEFAULT_RPC_URL,
        help=f"Ethereum JSON-RPC endpoint (default: {DEFAULT_RPC_URL})",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON array")
    parser.add_argument("--timeout", type=float, default=15.0, help="per-call RPC timeout (s)")
    args = parser.parse_args(argv)

    rpc_url = _check_url(args.rpc_url)
    rows: list[dict] = []
    failures = 0
    for address in args.addresses:
        try:
            rows.append(query_address(rpc_url, address, timeout=args.timeout))
        except (ValueError, RpcError) as exc:
            failures += 1
            print(f"{address}: ERROR {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(f"{row['address']}  {row['balance_eth']} ETH  nonce={row['nonce']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
