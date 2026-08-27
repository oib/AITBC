"""Who the escrow pays, and who is allowed to earn it (G2).

An escrow names its payee when the buyer creates it, but the job goes to whichever
miner polls next. Nothing used to connect the two, so a buyer could name any
address -- including their own -- and still have a real provider do the work.

These helpers are the single place that answers "which address has this miner
registered?" and "are these two spellings the same address?", so the payment path
and the dispatch path cannot drift apart on the answer.
"""

from __future__ import annotations

from typing import Any

from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.validation import validate_address

# A miner declares its payout address at registration, and it is stored in
# ``Miner.capabilities`` rather than ``Miner.extra_metadata`` on purpose:
# ``MinerService.heartbeat`` replaces ``extra_metadata`` wholesale on every beat,
# which would drop the wallet within seconds of registering.
WALLET_CAPABILITY_KEY = "wallet_address"


def same_address(left: str | None, right: str | None) -> bool:
    """Return True when both strings spell the same on-chain address.

    ``canonical_address`` returns the EIP-55 ``0x`` form for valid secp256k1
    addresses and lowercases anything else, so two spellings of the same valid
    address compare equal only if they are both ``0x``. A missing address is
    never equal to anything, including another missing one.
    """
    if not left or not right:
        return False
    return canonical_address(left) == canonical_address(right)


def looks_like_wallet_address(value: str | None) -> bool:
    """Return True when this string is a 0x address the chain could actually pay.

    Marketplace offers carry a ``provider_address`` field that is not always an
    address: live listings name ``aitbc-miner-1`` and ``aitbc3-provider`` there, and
    the CLI has its own copy of this test for the same reason. Escrow settles to the
    literal string it was given, so an offer that advertises a node id cannot price a
    job -- catching that at submit time is the difference between a rejected request
    and money locked to a payee that does not exist.

    The canonical form is what recovery produces: an EIP-55 ``0x`` address of forty
    hex digits. :func:`canonical_address` lowercases anything else, so legacy
    ``ait1``/``aitbc1`` spellings are rejected here.
    """
    if not value:
        return False
    return validate_address(canonical_address(value))


def miner_wallet_address(miner: Any) -> str | None:
    """Return the payout address a miner registered, or None if it declared none."""
    capabilities = getattr(miner, "capabilities", None) or {}
    value = capabilities.get(WALLET_CAPABILITY_KEY)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "WALLET_CAPABILITY_KEY",
    "looks_like_wallet_address",
    "miner_wallet_address",
    "same_address",
]
