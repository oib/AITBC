"""Provider-bond eligibility mapping for the market."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from aitbc.aitbc_logging import get_logger
from aitbc.exceptions import AITBCError
from aitbc.utils.units import units_to_ait
from sqlalchemy import JSON, Column, text, update
from sqlmodel import Field, Session, SQLModel, col, select

logger = get_logger(__name__)


class ProviderBondStatus(StrEnum):
    """Lifecycle status of a provider's required performance bond."""

    PENDING = "pending"
    ACTIVE = "active"
    LOCKED = "locked"
    SHORTFALL = "shortfall"
    LIQUIDATED = "liquidated"
    RELEASED = "released"


class ProviderBond(SQLModel, table=True):
    """Bond record that maps a provider to its current bond status."""

    __tablename__ = "provider_bond"
    __table_args__ = {"extend_existing": True}

    id: str = Field(
        default_factory=lambda: f"pb_{uuid4().hex[:10]}",
        max_length=32,
        primary_key=True,
    )
    provider_id: str = Field(default="", max_length=255, index=True)
    bond_id: str = Field(default="", max_length=255, index=True)
    status: str = Field(default=ProviderBondStatus.PENDING.value, max_length=20, index=True)
    amount: Decimal = Field(default=Decimal("0.0"), max_digits=20, decimal_places=8)
    required_amount: Decimal = Field(default=Decimal("0.0"), max_digits=20, decimal_places=8)
    meta: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default=text("'{}'")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


def _default_bond_min_amount() -> Decimal:
    """Global floor for provider-bond eligibility."""
    return Decimal(os.getenv("COORDINATOR_BOND_MIN_AMOUNT", "1"))


def is_provider_eligible(
    session: Session,
    provider_id: str,
    min_amount: Decimal | None = None,
) -> bool:
    """Return True if the provider has an active/locked bond that meets the floor.

    If ``min_amount`` is not supplied, the provider's own ``required_amount`` is
    used when set, otherwise the global ``COORDINATOR_BOND_MIN_AMOUNT`` floor.
    """
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
    bond = session.exec(statement).first()
    if bond is None:
        return False
    if bond.status not in {ProviderBondStatus.ACTIVE.value, ProviderBondStatus.LOCKED.value}:
        return False
    if min_amount is None:
        if bond.required_amount and bond.required_amount > 0:
            min_amount = bond.required_amount
        else:
            min_amount = _default_bond_min_amount()
    return bond.amount >= min_amount


# #1926: how long a chain verification stays fresh before the next
# eligibility read re-queries the node. Bounds the RPC cost of the
# read-through while keeping post-activation drift (release/slash)
# from surviving longer than the TTL.
_CHAIN_REVERIFY_ENV = "COORDINATOR_BOND_CHAIN_REVERIFY_SECONDS"
_DEFAULT_CHAIN_REVERIFY_SECONDS = 60.0


def _chain_reverify_ttl() -> float:
    try:
        return float(os.getenv(_CHAIN_REVERIFY_ENV, _DEFAULT_CHAIN_REVERIFY_SECONDS))
    except ValueError:
        return _DEFAULT_CHAIN_REVERIFY_SECONDS


_REVERIFIABLE_STATUSES = frozenset({ProviderBondStatus.ACTIVE.value, ProviderBondStatus.LOCKED.value})


def _meta_verified_at(meta: dict[str, Any]) -> datetime | None:
    raw = meta.get("chain_verified_at")
    if not isinstance(raw, str):
        return None
    try:
        verified_at = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return verified_at if verified_at.tzinfo is not None else verified_at.replace(tzinfo=UTC)


def _bond_wallet(session: Session, bond: ProviderBond) -> str | None:
    # The wallet the bond was verified against at creation is authoritative —
    # the miner's registered payout wallet may have changed since.
    wallet = (bond.meta or {}).get("chain_provider")
    if isinstance(wallet, str) and wallet:
        return wallet
    from ...infrastructure.domain.miner import Miner
    from ...payments.provider_binding import miner_wallet_address

    miner = session.get(Miner, bond.provider_id)
    return miner_wallet_address(miner) if miner is not None else None


def _apply_chain_entry(bond: ProviderBond, entry: dict[str, Any]) -> str | None:
    """Reconcile local status/amount from a chain bond entry.

    Returns the chain status, or ``None`` when the chain reports a status the
    projection cannot map — the caller fails closed in that case.
    """
    raw_status = entry.get("status")
    chain_status = raw_status if isinstance(raw_status, str) else ""
    if chain_status == "released":
        bond.status = ProviderBondStatus.RELEASED.value
    elif chain_status == "slashed":
        bond.status = ProviderBondStatus.LIQUIDATED.value
    elif chain_status != "active":
        # Unknown chain status — cannot reconcile, fail closed.
        return None
    # "active" leaves local ACTIVE/LOCKED standing — LOCKED is local job
    # bookkeeping the chain does not track.
    chain_amount = units_to_ait(int(entry.get("amount") or 0))
    if chain_amount != bond.amount:
        bond.amount = chain_amount
    return chain_status


def reconcile_provider_bond(session: Session, provider_id: str) -> ProviderBond | None:
    """Re-verify an ACTIVE/LOCKED bond projection against chain state (#1926).

    The local ``ProviderBond`` row is a projection refreshed on writes; a bond
    released or slashed on-chain after activation would otherwise keep
    qualifying until the next local write. This re-queries
    ``GET /rpc/bond/provider/{wallet}`` and reconciles status/amount.

    Returns the (possibly updated) ``ProviderBond`` row, or ``None`` when the
    chain could not be consulted — RPC failure, no resolvable wallet, or no
    ``bond_id`` to match. Money-moving callers must treat ``None`` as
    ineligible (fail closed); read paths may fall back to the local row.

    Only ``active``/``locked`` local states are re-checked: they are the only
    ones that can grant eligibility, and dead states need no chain truth.
    Re-checks are TTL-bounded via ``meta["chain_verified_at"]`` so the
    eligibility scan does not pay an RPC per miner per job.
    """
    bond = session.exec(select(ProviderBond).where(ProviderBond.provider_id == provider_id)).first()
    if bond is None:
        return None
    if bond.status not in _REVERIFIABLE_STATUSES:
        return bond
    meta = bond.meta or {}
    verified_at = _meta_verified_at(meta)
    if verified_at is not None and (datetime.now(UTC) - verified_at).total_seconds() < _chain_reverify_ttl():
        return bond
    wallet = _bond_wallet(session, bond)
    if not wallet or not bond.bond_id:
        return None
    try:
        from ...blockchain.services.blockchain import BlockchainService

        chain = BlockchainService().list_provider_bonds(wallet)
    except AITBCError as exc:
        logger.warning("Provider-bond chain re-verify failed for %s: %s", provider_id, exc)
        return None
    entry = next((b for b in chain.get("bonds", []) if str(b.get("bond_id")) == str(bond.bond_id)), None)
    now = datetime.now(UTC)
    chain_status: str | None
    if entry is None:
        # Chain-verified absence: no such bond for this wallet on-chain.
        bond.status = ProviderBondStatus.RELEASED.value
        chain_status = "absent"
    else:
        chain_status = _apply_chain_entry(bond, entry)
        if chain_status is None:
            return None
    bond.meta = {**meta, "chain_status": chain_status, "chain_verified_at": now.isoformat()}
    bond.updated_at = now
    session.add(bond)
    session.flush()
    session.refresh(bond)
    return bond


def set_provider_bond_status(
    session: Session,
    provider_id: str,
    status: ProviderBondStatus,
    amount: Decimal | None = None,
    required_amount: Decimal | None = None,
    bond_id: str = "",
) -> ProviderBond:
    """Upsert the bond status for a provider.

    ``amount`` and ``required_amount`` are preserved when not explicitly
    supplied, so lock/release/slash operations do not accidentally zero the bond.
    """
    statement = select(ProviderBond).where(ProviderBond.provider_id == provider_id)
    bond = session.exec(statement).first()
    if bond is None:
        bond = ProviderBond(provider_id=provider_id)
        session.add(bond)
    bond.status = status.value if isinstance(status, ProviderBondStatus) else status
    if amount is not None:
        bond.amount = amount
    if required_amount is not None:
        bond.required_amount = required_amount
    if bond_id:
        bond.bond_id = bond_id
    bond.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(bond)
    return bond


def apply_bond_slash_cas(
    session: Session,
    bond_pk: str,
    *,
    expected_amount: Decimal,
    expected_updated_at: datetime,
    new_amount: Decimal,
    status: ProviderBondStatus,
    meta: dict[str, Any],
) -> ProviderBond | None:
    """Apply an off-chain bond slash only when the row still matches our snapshot.

    ``provider_id`` is not unique — automatic slashing binds by primary key and
    uses amount+updated_at as the compare-and-swap guard so concurrent slashes
    cannot clobber each other or the wrong sibling row.
    """
    now = datetime.now(UTC)
    result = session.execute(
        update(ProviderBond)
        .where(col(ProviderBond.id) == bond_pk)
        .where(col(ProviderBond.amount) == expected_amount)
        .where(col(ProviderBond.updated_at) == expected_updated_at)
        .values(
            amount=new_amount,
            status=status.value if isinstance(status, ProviderBondStatus) else status,
            meta=meta,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:
        session.rollback()
        return None
    session.commit()
    return session.get(ProviderBond, bond_pk)
