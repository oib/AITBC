"""Retired protocol-transfer RPC surfaces (BNT-2, operator decision 2026-10-12).

Every transaction ``queue_protocol_transfer`` emits is unsigned at the top
level (the protocol escrow is keyless) and ``v9_signature_verdict`` exempts
only ``BRIDGE_*`` — so staking, agent staking, AUTO_STAKE, bounty and HTLC
transactions can never seal at block version ≥ 9. Before this module the
RPCs accepted the request, wrote a local domain row and queued a tx that
sat pending forever (BNT-1 audit: zero sealed since height 30400).

The surfaces now refuse up front with HTTP 410; apply code and the
production-shape replay pins in ``test_v9_type_coverage_replay.py`` are
untouched. The retirement is unconditional — there is no flag and no
revival path; a future consensus version that admits ``payload.auth``
would be a new implementation, not a toggle.

v17 (BNT-1 revival, operator ruling 28 Oct): staking, agent staking and
bounty emissions already carry ``payload.auth``, so their surfaces are
restored behind the ``protocol_transfers_active`` gate — still a
refusal-first 410 via :func:`raise_for_unarmed` while the
``state_transition_v17_height`` pin is unset or unreached, live once a
block at the next height would apply v17 rules. HTLC and AUTO_STAKE emit
no auth at all and stay retired under ``raise_for_retired`` /
``RetiredProtocolTransfer``.
"""

from typing import NoReturn

from fastapi import HTTPException

_RETIRED_REASON = (
    "{feature} is retired: protocol-escrow transfers cannot seal at block version 9 "
    "and no transaction would ever confirm. See docs/design/v9-unsigned-protocol-transfers.md."
)

_UNARMED_REASON = (
    "{feature} is not active on this chain: protocol-escrow transfers require "
    "state-transition v17 (state_transition_v17_height unset or not yet reached) "
    "and no transaction would ever confirm below it."
)


class RetiredProtocolTransfer(RuntimeError):
    """Raised by non-HTTP entry points (e.g. HTLCContract mutators)."""


def raise_for_retired(feature: str) -> NoReturn:
    raise HTTPException(status_code=410, detail=_RETIRED_REASON.format(feature=feature))


def raise_for_retired_contract(feature: str) -> NoReturn:
    raise RetiredProtocolTransfer(_RETIRED_REASON.format(feature=feature))


def raise_for_unarmed(feature: str) -> NoReturn:
    """Refuse a revived surface while the v17 admission rule is unarmed.

    Same HTTP 410 the unconditional retirement returned — the feature is
    dormant, not gone, and wakes by itself once the pin height passes.
    """
    raise HTTPException(status_code=410, detail=_UNARMED_REASON.format(feature=feature))
