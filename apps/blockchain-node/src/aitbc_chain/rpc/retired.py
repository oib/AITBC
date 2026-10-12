"""Retired protocol-transfer RPC surfaces (BNT-2, operator decision 2026-10-12).

Every transaction ``queue_protocol_transfer`` emits is unsigned at the top
level (the protocol escrow is keyless) and ``v9_signature_verdict`` exempts
only ``BRIDGE_*`` — so staking, agent staking, AUTO_STAKE, bounty and HTLC
transactions can never seal at block version ≥ 9. Before this module the
RPCs accepted the request, wrote a local domain row and queued a tx that
sat pending forever (BNT-1 audit: zero sealed since height 30400).

The surfaces now refuse up front with HTTP 410; apply code and the
production-shape replay pins in ``test_v9_type_coverage_replay.py`` are
untouched. If a future consensus version admits ``payload.auth``, flip
``PROTOCOL_TRANSFER_RPC_RETIRED`` to False — tests will flag the revival.
"""

from fastapi import HTTPException

PROTOCOL_TRANSFER_RPC_RETIRED = True

_RETIRED_REASON = (
    "{feature} is retired: protocol-escrow transfers cannot seal at block version 9 "
    "and no transaction would ever confirm. See docs/design/v9-unsigned-protocol-transfers.md."
)


class RetiredProtocolTransfer(RuntimeError):
    """Raised by non-HTTP entry points (e.g. HTLCContract mutators)."""


def is_retired() -> bool:
    return PROTOCOL_TRANSFER_RPC_RETIRED


def raise_for_retired(feature: str) -> None:
    if PROTOCOL_TRANSFER_RPC_RETIRED:
        raise HTTPException(status_code=410, detail=_RETIRED_REASON.format(feature=feature))


def raise_for_retired_contract(feature: str) -> None:
    if PROTOCOL_TRANSFER_RPC_RETIRED:
        raise RetiredProtocolTransfer(_RETIRED_REASON.format(feature=feature))
