"""Strict parsers for bridge-monitor RPC account responses (#3041).

Mirrors ``_parse_account_nonce`` in coordinator-api's bond_slashing.py
(#3015): a 200 account response counts as field truth only when it carries
a real non-negative integer — explicit ``0`` included. A missing, null,
string, bool or negative value is a malformed response, NOT a fabricated
zero: return ``None`` so the caller treats it like a failed probe.

The failure direction matters per call site:

- ``_build_signed_transfer`` signs whatever nonce it reads — a fabricated
  0 produces a doomed envelope, a mempool rejection, and (once the
  abandon proof passes) an unbudgeted re-sign loop that gates the
  serialized payout slot.
- ``_account_nonce`` feeds the abandon proof — a fabricated 0 reads as
  "nonce not passed" and refuses the abandon (fail-closed).
- ``_payout_wallet_balance`` feeds the payout cap — a fabricated 0 reads
  as "balance unknown/empty" and blocks payouts (fail-closed).

All three must agree on what "malformed" means so a response that one
path rejects cannot be silently reinterpreted by another.
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
    """Strict ``nonce`` parse for ``/rpc/account/{address}`` responses."""
    return parse_uint_field(payload, "nonce")


def parse_account_balance(payload: Any) -> int | None:
    """Strict ``balance`` parse for ``/rpc/account/{address}`` responses."""
    return parse_uint_field(payload, "balance")
