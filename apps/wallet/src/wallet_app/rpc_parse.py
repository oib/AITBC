"""Strict parsers for wallet RPC account responses (#3044).

Mirrors ``bridge_monitor.rpc_parse`` (#3041) and ``_parse_account_nonce``
in coordinator-api's bond_slashing.py (#3015): a 200 account response
counts as field truth only when it carries a real non-negative integer —
explicit ``0`` included. A missing, null, string, bool, float or negative
value is a malformed response, NOT a fabricated zero: return ``None`` so
the caller treats it like a failed probe and fails closed (no sign).

``int(data.get("nonce", 0))`` used to answer 0 for every one of those
shapes — a fabricated nonce signs a doomed envelope (nonce conflict at
the node), which on the shared-payout-account lanes also burns the
serialized payout slot.
"""

from typing import Any


def parse_uint_field(payload: Any, field: str) -> int | None:
    """Return ``payload[field]`` only for a real non-negative int.

    ``bool`` is excluded (``True`` is an ``int`` in Python but is never a
    nonce/balance); explicit ``0`` is valid — a fresh account really does
    sit at nonce 0 and a drained wallet really does hold 0 units.
    """
    if not isinstance(payload, dict):
        return None
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def parse_account_nonce(payload: Any) -> int | None:
    """Strict ``nonce`` parse for ``/rpc/account(s)/{address}`` responses."""
    return parse_uint_field(payload, "nonce")


def parse_account_balance(payload: Any) -> int | None:
    """Strict ``balance`` parse for ``/rpc/account(s)/{address}`` responses."""
    return parse_uint_field(payload, "balance")


def require_account_nonce(payload: Any, *, context: str) -> int:
    """Strict nonce parse that raises ``ValueError`` on a malformed payload.

    ``context`` names what was being fetched (an address) for the error
    message. Every caller's failure path already treats ``ValueError`` as
    an ops error, so this fails closed with no sign — and keeps the
    cyclomatic complexity of call sites unchanged (no new branch).
    """
    nonce = parse_account_nonce(payload)
    if nonce is None:
        raise ValueError(f"malformed account nonce in RPC response for {context}")
    return nonce


def require_account_view(payload: Any, *, address: str) -> tuple[int, int]:
    """Strict ``(nonce, balance)`` parse for ``/rpc/account/{address}``.

    Both fields feed downstream decisions — the nonce signs escrow sweep
    envelopes, the balance gates the fee float — so a malformed 200 raises
    ``ValueError`` rather than fabricating a 0.
    """
    nonce = parse_account_nonce(payload)
    balance = parse_account_balance(payload)
    if nonce is None or balance is None:
        raise ValueError(f"malformed account response for {address}")
    return nonce, balance
