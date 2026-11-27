"""Strict parsers for coordinator-api RPC account responses (#3057).

Mirrors ``_parse_account_nonce`` in market/services/bond_slashing.py
(#3015), ``bridge_monitor.rpc_parse`` (#3041) and ``wallet_app.rpc_parse``
(#3044): a 200 account response counts as field truth only when it carries
a real non-negative integer — explicit ``0`` included. A missing, null,
string, bool, float or negative value is a malformed response, NOT a
fabricated zero: return ``None`` so the caller treats it like a failed
probe and fails closed (no sign).

``int(payload.get("nonce", 0))`` used to answer 0 for every one of those
shapes — a fabricated nonce signs a doomed envelope (nonce conflict at
the node), which on the escrow-lock path means the payment row believes
signing succeeded while the lock never lands.
"""

from typing import Any


def parse_uint_field(payload: Any, field: str) -> int | None:
    """Return ``payload[field]`` only for a real non-negative int.

    ``bool`` is excluded (``True`` is an ``int`` in Python but is never a
    nonce); explicit ``0`` is valid — a fresh account really does sit at
    nonce 0.
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
