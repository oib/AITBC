"""Bond lock/slash/release verdicts and bond escrow/burn addresses.

Pure-move split out of ``state_transition.py``: the state-transition facade
re-exports every name defined here, so ``from aitbc_chain.state.state_transition
import X`` keeps working unchanged for all of them.

Import ``aitbc_chain.state.state_transition`` first (it wires this module in);
this module is not meant to be imported directly.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from eth_utils import keccak
from sqlmodel import Session, select

from ..base_models import Bond, _to_ait_address
from ..models import Account
from ..v24_rules import v24_rules_is_active
from aitbc.crypto.signature_recovery import canonical_address
from . import state_transition as _st


_BOND_ESCROW_ADDRESS = os.getenv("BOND_ESCROW_ADDRESS", "")
if _BOND_ESCROW_ADDRESS:
    _BOND_ESCROW_ADDRESS = canonical_address(_BOND_ESCROW_ADDRESS)
else:
    _BOND_ESCROW_ADDRESS = canonical_address("0x" + keccak(b"aitbc.bond.escrow").hex()[:40])

_BOND_BURN_ADDRESS = os.getenv("BOND_BURN_ADDRESS", "")
if _BOND_BURN_ADDRESS:
    _BOND_BURN_ADDRESS = canonical_address(_BOND_BURN_ADDRESS)
else:
    _BOND_BURN_ADDRESS = canonical_address("0x" + keccak(b"aitbc.bond.burn").hex()[:40])


def _bond_escrow_ait() -> str:
    return _to_ait_address(_BOND_ESCROW_ADDRESS)


def _bond_burn_ait() -> str:
    return _to_ait_address(_BOND_BURN_ADDRESS)


def _is_bond_escrow(address: str) -> bool:
    return canonical_address(address) == _BOND_ESCROW_ADDRESS


def _is_bond_burn(address: str) -> bool:
    return canonical_address(address) == _BOND_BURN_ADDRESS


# v22 (BOND-RELEASE-001, BOND-LOCK-TOPUP-PROVIDER-MISMATCH, #1166/#1167):
# compile-time protocol constant — no env, config or chain parameter may
# influence it (spec v2.2 §4.4). Every bond becomes releasable no later
# than created_at + this horizon, regardless of top-up count.
PROTOCOL_MAX_LOCK_DURATION = timedelta(days=3650)


def bond_tx_verdict(
    session: Session,
    chain_id: str,
    tx_type: str,
    payload: Any,
    sender: str,
    recipient: str,
    value: Any,
    *,
    block_version: int,
    block_time: datetime | None,
    block_height: int | None = None,
) -> str | None:
    """v22 bond authorization verdict — None when the op may proceed.

    Shared by ``validate_transaction``, mempool admission and (as
    defense-in-depth) ``_handle_bond_transaction``. Pure function of
    (tx, persisted rows, sealed ``block_time``): no wall-clock, env or
    node-local reads. Inert below ``block_version 22`` and for
    ``BOND_SLASH`` (authority-gated, unchanged).

    Enforces spec v2.2: mandatory ``payload.provider`` bound to the
    signer AND the persisted ``bond.provider``; absolute lock ceiling
    ``min(now + lock_days, created_at + PROTOCOL_MAX_LOCK_DURATION)``;
    post-ceiling and NULL-expiry refusals; zero-mutation hard rejects.
    """
    if block_version < 22 or tx_type not in ("BOND_LOCK", "BOND_RELEASE"):
        return None
    payload = payload if isinstance(payload, dict) else {}
    bond_id = payload.get("bond_id")
    if not bond_id:
        return "missing bond_id in payload"
    provider = payload.get("provider")
    if not provider:
        return "missing provider in payload"
    sender_addr = _to_ait_address(sender or "")
    if _to_ait_address(provider or "") != sender_addr:
        return "not signed by the bond provider"
    now = _bond_verdict_now(block_time)
    if tx_type == "BOND_LOCK":
        return _bond_lock_verdict(session, chain_id, bond_id, payload, sender_addr, recipient, value, now=now)
    return _bond_release_verdict(
        session, chain_id, bond_id, sender_addr, recipient, value, now=now, block_version=block_version
    )


def _bond_verdict_now(block_time: datetime | None) -> datetime:
    """Sealed block time (UTC-normalized); wall-clock only for non-consensus callers."""
    now = block_time if block_time is not None else datetime.now(UTC)
    return now if now.tzinfo is not None else now.replace(tzinfo=UTC)


def _bond_lock_verdict(
    session: Session,
    chain_id: str,
    bond_id: str,
    payload: dict[str, Any],
    sender_addr: str,
    recipient: str,
    value: Any,
    *,
    now: datetime,
) -> str | None:
    """v22 BOND_LOCK verdict: escrow recipient, positive int value, bounded
    lock_days, then new-bond or persisted-provider top-up rules."""
    if not _is_bond_escrow(_to_ait_address(recipient or "")):
        return "recipient is not the bond escrow address"
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return "non-positive lock value"
    try:
        lock_days = int(payload.get("lock_days", 30))
    except (TypeError, ValueError, OverflowError):
        return "BOND_LOCK refused: invalid lock_days"
    if not 1 <= lock_days <= 3650:
        return "BOND_LOCK refused: lock_days out of range (1-3650)"
    existing = session.exec(select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id)).first()
    if existing is None:
        return None
    return _bond_topup_verdict(existing, bond_id, sender_addr, value, now=now)


def _bond_topup_verdict(existing: Bond, bond_id: str, sender_addr: str, value: int, *, now: datetime) -> str | None:
    """v22 top-up rules on an existing bond row: active status, persisted
    provider binding, absolute ceiling from immutable created_at, int64 bound."""
    if existing.status != "active":
        return f"BOND_LOCK top-up refused: bond {bond_id} is {existing.status}, not active"
    if _to_ait_address(existing.provider or "") != sender_addr:
        return "BOND_LOCK top-up refused: signer is not the bond provider"
    created = existing.created_at or now
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if now >= created + PROTOCOL_MAX_LOCK_DURATION:
        return f"BOND_LOCK refused: bond {bond_id} lock horizon exhausted"
    if existing.amount + value > 2**63 - 1:
        return "BOND_LOCK refused: bond amount overflow"
    return None


def _bond_release_verdict(
    session: Session,
    chain_id: str,
    bond_id: str,
    sender_addr: str,
    recipient: str,
    value: Any,
    *,
    now: datetime,
    block_version: int,
) -> str | None:
    """v22 BOND_RELEASE verdict: provider recipient, zero value, active bond,
    persisted-provider binding, expiry/amount/escrow sufficiency."""
    if _to_ait_address(recipient or "") != sender_addr:
        return "recipient must be the provider"
    if value != 0:
        return "must have value=0"
    bond = session.exec(
        select(Bond).where(Bond.chain_id == chain_id, Bond.bond_id == bond_id, Bond.status == "active")
    ).first()
    if not bond:
        return f"unknown or inactive bond {bond_id}"
    if _to_ait_address(bond.provider or "") != sender_addr:
        return "not signed by the bond provider"
    return _bond_release_row_verdict(session, chain_id, bond, bond_id, now, block_version=block_version)


def _bond_release_row_verdict(
    session: Session, chain_id: str, bond: Bond, bond_id: str, now: datetime, *, block_version: int
) -> str | None:
    """Expiry (NULL fails closed), positive amount, escrow sufficiency."""
    if bond.locked_until is None:
        return "no lock expiry recorded"
    locked_until = bond.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    if now < locked_until:
        return f"lock period for {bond_id} has not expired"
    if bond.amount <= 0:
        return "bond has nothing to release"
    if block_version >= 24 or v24_rules_is_active():
        # #1314 V3: authoritative scalar escrow-balance read — bypasses
        # identity-map staleness. The version term covers admission callers
        # outside the apply contextvar; the contextvar covers in-apply ones.
        _bal, _nonce, escrow_exists = _st.read_current_account(session, chain_id, _BOND_ESCROW_ADDRESS)
        escrow_balance = _bal if _bal is not None else 0
        escrow_missing = not escrow_exists
    else:
        escrow = session.get(Account, (chain_id, _BOND_ESCROW_ADDRESS))
        escrow_balance = escrow.balance if escrow is not None else 0
        escrow_missing = escrow is None
    if escrow_missing or escrow_balance < bond.amount:
        return f"escrow balance {escrow_balance} below release amount {bond.amount}"
    return None
