"""Governance terminal review of provider-bond slash appeals (#2966).

``POST /governance/slash-appeals`` only records a dispute; this module is the
operator-side resolution. ``accepted`` can clear a *local marking* — it never
moves funds and never reverses a sealed on-chain BOND_SLASH. Two markings
qualify:

- ``legacy`` — the retired manual ``bonds/slash`` route wrote
  ``slash_reason``/``slashed_by`` into bond meta and set ``liquidated`` with
  no chain event behind it. Acceptance requires the chain point-read to show
  the bond ``active`` with ``slashed_tx_hash`` unset.
- ``suspended`` — the operator suspension is an orthogonal meta flag
  (``suspension_event_id`` plus audit fields), not a ``ProviderBond.status``,
  so the automatic slasher keeps selecting the bond and in-flight violations
  stay punishable. Acceptance restores from the *fresh* chain balance: a
  partial automatic slash while suspended is never undone.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlmodel import Session, col, select

from aitbc.aitbc_logging import get_logger
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.exceptions import AITBCError
from aitbc.utils.units import units_to_ait

from ...blockchain.services.blockchain import BlockchainService
from ...market.domain.provider_bond import (
    ProviderBond,
    ProviderBondStatus,
    _default_bond_min_amount,
    projected_bond_status,
    stage_bond_projection,
    suspension_event_id,
)
from ..domain.slash_appeal import SlashAppeal, SlashAppealStatus

logger = get_logger(__name__)

_RESOLVABLE_APPEAL_STATUSES = frozenset({SlashAppealStatus.SUBMITTED.value, SlashAppealStatus.UNDER_REVIEW.value})


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _require_chain_provider(provider: Any, *, expected_provider: str) -> None:
    """The chain record's provider must canonical-match the bond's wallet."""
    if not isinstance(provider, str) or not provider:
        raise _conflict("chain bond record has no provider")
    try:
        chain_provider = canonical_address(provider, strict=True)
    except ValueError as e:
        raise _conflict("chain bond provider is not a canonical EVM address") from e
    if chain_provider != expected_provider:
        raise _conflict("chain bond belongs to a different provider wallet")


def _require_chain_amount(amount: Any) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise _conflict("chain bond amount is missing or invalid")


def _require_slash_hash_state(chain: dict[str, Any], *, legacy: bool) -> None:
    """The point-read must explicitly report ``slashed_tx_hash``.

    Legacy acceptance demands ``None`` — any recorded hash means a real burn
    the local marking must not clear (the local meta ``slash_tx_hash`` is
    never consulted: older actions stored unrelated ids there). Suspension
    acceptance tolerates a hash — an automatic slash while suspended
    legitimately writes one — but it must be well-formed.
    """
    if "slashed_tx_hash" not in chain:
        raise _conflict("chain bond record does not report slashed_tx_hash")
    slash_hash = chain["slashed_tx_hash"]
    if legacy:
        if slash_hash is not None:
            raise _conflict("chain records a slash for this bond; it cannot be cleared locally")
    elif slash_hash is not None and not (isinstance(slash_hash, str) and slash_hash):
        raise _conflict("chain slashed_tx_hash is malformed")


def _require_unburned_active(chain: Any, *, bond_id: str, expected_provider: str, legacy: bool) -> None:
    """Fail closed (409) unless the chain record proves an unburned active bond."""
    if not isinstance(chain, dict) or chain.get("success") is not True:
        raise _conflict("chain did not confirm the bond record")
    if chain.get("bond_id") != bond_id:
        raise _conflict("chain bond record does not match the appealed bond_id")
    _require_chain_provider(chain.get("provider"), expected_provider=expected_provider)
    if chain.get("status") != "active":
        raise _conflict(f"on-chain bond is {chain.get('status')}, not active")
    _require_chain_amount(chain.get("amount"))
    _require_slash_hash_state(chain, legacy=legacy)


def _verify_chain_active_bond(bond: ProviderBond, meta: dict[str, Any], *, legacy: bool) -> tuple[Decimal, int]:
    """Fresh chain point-read proving the bond is active and unburned.

    Returns ``(amount_ait, amount_units)`` from the authoritative chain
    record. The provider wallet comes only from the bond's creation-time
    ``meta["chain_provider"]`` — the miner's registered wallet may have
    changed since and is never a fallback here.
    """
    raw_provider = meta.get("chain_provider")
    if not isinstance(raw_provider, str) or not raw_provider:
        raise _conflict("bond meta has no chain_provider to verify the appeal against")
    try:
        expected_provider = canonical_address(raw_provider, strict=True)
    except ValueError as e:
        raise _conflict("bond meta chain_provider is not a canonical EVM address") from e
    # Sole caller of BlockchainService.get_bond: refuse dot-segments before
    # they reach the /bond/{id} path — a clean 409 instead of an RPC round-trip.
    if bond.bond_id in {".", ".."}:
        raise _conflict("bond_id cannot be verified against chain state")
    try:
        chain = BlockchainService().get_bond(bond.bond_id)
    except AITBCError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="could not verify bond against chain state",
        ) from e
    _require_unburned_active(chain, bond_id=bond.bond_id, expected_provider=expected_provider, legacy=legacy)
    amount_units: int = chain["amount"]
    return units_to_ait(amount_units), amount_units


def _appeal_target_state(bond: ProviderBond, appeal: SlashAppeal) -> tuple[bool, bool]:
    """Classify the bond for acceptance -> ``(legacy, suspended)``.

    ``legacy`` is the retired manual-slash marking: a LIQUIDATED row carrying
    the old meta markers, bound to the same ``chain_bond_id`` it was created
    with, with no suspension flag and no appeal event id. ``suspended`` is the
    orthogonal meta flag on a still-eligible underlying status whose
    ``suspension_event_id`` the appeal names.
    """
    meta = bond.meta or {}
    legacy = (
        bond.status == ProviderBondStatus.LIQUIDATED.value
        and not appeal.slash_event_id
        and bool(meta.get("slash_reason"))
        and bool(meta.get("slashed_by"))
        and not meta.get("suspension_event_id")
        and meta.get("chain_bond_id") == bond.bond_id
    )
    suspension_event = suspension_event_id(bond)
    suspended = suspension_event is not None and appeal.slash_event_id == suspension_event
    return legacy, suspended


def _restored_bond_status(bond: ProviderBond, *, suspended: bool, chain_amount: Decimal, floor: Decimal) -> str:
    """Projected status after acceptance.

    A suspended bond that was LOCKED keeps its job lock when the fresh chain
    balance still clears the floor — the chain cannot see the lock. Every
    other case follows the ACTIVE/SHORTFALL floor rules.
    """
    if suspended and bond.status == ProviderBondStatus.LOCKED.value and chain_amount >= floor:
        return ProviderBondStatus.LOCKED.value
    if chain_amount >= floor:
        return ProviderBondStatus.ACTIVE.value
    return ProviderBondStatus.SHORTFALL.value


def _stage_accepted_bond(
    session: Session,
    bond: ProviderBond,
    appeal: SlashAppeal,
    reviewer: str,
    now: datetime,
) -> str:
    """Stage the accepted-appeal bond restore; returns the restored status.

    Everything through the compare-and-swap write happens here so the caller
    can pair it with the appeal transition in one commit — a stale row rolls
    both back (409). Only the suspension flag is lifted; slash and suspension
    audit stay in meta.
    """
    meta = bond.meta or {}
    legacy, suspended = _appeal_target_state(bond, appeal)
    if not (legacy or suspended):
        raise _conflict("bond is not in a resolvable slashed or suspended state")
    chain_amount, chain_amount_units = _verify_chain_active_bond(bond, meta, legacy=legacy)
    floor = max(_default_bond_min_amount(), bond.required_amount)
    restored_status = _restored_bond_status(bond, suspended=suspended, chain_amount=chain_amount, floor=floor)
    # Lift only the suspension flag; every other meta key — slash audit,
    # historical slash ids, suspension audit — is retained. The appeal's
    # chain read is proof for THIS decision only: never seed the reconcile
    # TTL cache from it (an automatic slash can seal during or after that
    # read), so the next dispatch re-verifies on-chain.
    resolved_meta = {key: value for key, value in meta.items() if key != "suspension_event_id"}
    resolved_meta.pop("chain_verified_at", None)
    resolved_meta.update(
        {
            "chain_status": "active",
            "chain_amount_units": chain_amount_units,
            "appeal_chain_verified_at": now.isoformat(),
            "appeal_resolution_id": appeal.id,
            "appeal_resolved_by": reviewer,
        }
    )
    if suspended:
        resolved_meta["resolved_suspension_event_id"] = appeal.slash_event_id
    if not stage_bond_projection(
        session,
        bond,
        status=restored_status,
        amount=chain_amount,
        meta=resolved_meta,
    ):
        session.rollback()
        raise _conflict("bond changed while the appeal was being resolved; retry")
    return restored_status


def resolve_slash_appeal(
    session: Session,
    appeal_id: str,
    *,
    decision: Literal["accepted", "rejected"],
    reviewer: str,
    notes: str,
) -> dict[str, Any]:
    """Resolve an open slash appeal; returns the terminal record.

    ``accepted`` restores the local bond projection only after the checks
    above pass, inside the same transaction as the appeal transition — a
    stale snapshot on either row rolls both back (409). ``rejected`` leaves
    the bond untouched.
    """
    appeal = session.get(SlashAppeal, appeal_id)
    if appeal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="slash appeal not found")
    if appeal.status not in _RESOLVABLE_APPEAL_STATUSES:
        raise _conflict(f"slash appeal is {appeal.status}; only submitted/under_review appeals can be resolved")
    bond = session.exec(
        select(ProviderBond).where(
            ProviderBond.bond_id == appeal.bond_id,
            ProviderBond.provider_id == appeal.provider_id,
        )
    ).first()
    if bond is None:
        raise _conflict("no bond matches the appeal's provider_id/bond_id")

    now = datetime.now(UTC)
    if decision == "accepted":
        bond_status = _stage_accepted_bond(session, bond, appeal, reviewer, now)
    else:
        bond_status = projected_bond_status(bond)
    appeal_result = session.execute(
        update(SlashAppeal)
        .where(col(SlashAppeal.id) == appeal.id)
        .where(col(SlashAppeal.status) == appeal.status)
        .where(col(SlashAppeal.updated_at) == appeal.updated_at)
        .values(status=decision, reviewer_notes=notes, updated_at=now)
        .execution_options(synchronize_session=False)
    )
    if getattr(appeal_result, "rowcount", 0) != 1:
        session.rollback()
        raise _conflict("appeal changed while being resolved; retry")
    session.commit()
    logger.info("slash appeal %s resolved as %s by %s", appeal.id, decision, reviewer)

    return {
        "id": appeal.id,
        "bond_id": appeal.bond_id,
        "provider_id": appeal.provider_id,
        "status": decision,
        "bond_status": bond_status,
        "funds_moved": False,
    }
