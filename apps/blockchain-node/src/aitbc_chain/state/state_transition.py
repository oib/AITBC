"""
State Transition Layer for AITBC

This module provides the StateTransition class that validates all state changes
to ensure they only occur through validated transactions.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, NamedTuple

from eth_utils import keccak
from sqlalchemy import func
from sqlmodel import Session, select

from ..config import settings
from ..logger import get_logger
from ..metrics import metrics_registry
from ..v24_rules import v24_rules_active, v24_rules_is_active
from .authoritative_reads import read_current_account
from ..base_models import (
    Block,
    Bond,
    ChainParameter,
    ChainParameterHistory,
    _to_ait_address,
)
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS
from ..models import Account, Transaction
from ..rpc.utils import verify_transaction_signature
from .bridge_credit import (
    bridge_refund_lock_hash,
)
from .agent_spend import (
    AGENT_SESSION_TX_TYPES,
)
from .pure_state_transition import (
    DEFAULT_ESCROW_FEE_CAP_BPS,
    MAX_ESCROW_FEE_CAP_BPS,
)
from .v13_policy import count_v13_shadow_checked, count_v13_would_reject

try:
    from aitbc.caching import RedisCache

    _REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _cache: RedisCache | None = RedisCache(redis_url=_REDIS_URL, default_ttl=30)
except Exception:
    _cache = None
logger = get_logger(__name__)

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

# Transaction types that are forbidden from carrying value at consensus level.
# GPU_MARKET is included because every legitimate action (offer,
# software_offer, software_job, cancel, rating) is a value-zero record; there is
# no dedicated branch for it in apply_transaction, so a nonzero amount would
# execute as a plain transfer.
_ZERO_VALUE_TX_TYPES = frozenset(
    {"MESSAGE", "GOVERNANCE_EXECUTE", "GPU_REGISTER", "GPU_ALLOCATE", "GPU_MARKET", "VALIDATOR_DEACTIVATE"}
)

# v25 (#1566): GPURegistration.price_per_hour is Numeric(20,8) — at most 12
# integer digits. The bound mirrors the coordinator-side
# _validated_price_per_hour (#1389/#1566): finite, >= 0, <= column max.
_GPU_PRICE_PER_HOUR_MAX = Decimal("999999999999.99999999")


def _gpu_price_per_hour_in_range(price: Decimal) -> bool:
    """v25 GPU_REGISTER price bound: finite Decimal in [0, Numeric(20,8) max]."""
    return price.is_finite() and Decimal("0") <= price <= _GPU_PRICE_PER_HOUR_MAX


def _is_zero_value_tx_type(tx_type: str, block_version: int) -> bool:
    """Whether ``tx_type`` may not carry value under the rules of ``block_version``.

    GPU_DEREGISTER joins the set from v10 only: below it the name has no consensus meaning and a block carrying it
    replays as the plain transfer it always was.
    """
    if tx_type in _ZERO_VALUE_TX_TYPES or (block_version >= 10 and tx_type == "GPU_DEREGISTER"):
        return True
    # v21: session lifecycle txs move no value — the owner pays only the fee.
    return block_version >= 21 and tx_type in AGENT_SESSION_TX_TYPES


def _chain_parameter_value(session: Session, chain_id: str, parameter: str, block_height: int | None = None) -> str | None:
    """Return the ``chain_parameter`` value in force at ``block_height``.

    ``chain_parameter_history`` records the height each value took effect;
    the latest entry at or below the height being validated wins. The
    current-value row is the fallback: it applies when its ``applied_height``
    is at or below ``block_height``, and at every height when
    ``applied_height`` is NULL (rows written before height tracking, or
    operator-seeded outside the apply path — "set at an unknown height"
    keeps the pre-tracking status quo). A parameter whose only recorded
    effect is after ``block_height`` resolves as unset for that block:
    replaying history can never fail because a value was set later in the
    chain. ``block_height=None`` returns the current value, for callers with
    no block context.
    """
    if block_height is not None:
        hist = session.exec(
            select(ChainParameterHistory)
            .where(
                ChainParameterHistory.chain_id == chain_id,
                ChainParameterHistory.parameter == parameter,
                ChainParameterHistory.applied_height <= block_height,
            )
            .order_by(ChainParameterHistory.applied_height.desc())  # type: ignore[attr-defined]
        ).first()
        if hist is not None:
            return hist.value
    row = session.exec(
        select(ChainParameter).where(
            ChainParameter.chain_id == chain_id,
            ChainParameter.parameter == parameter,
        )
    ).first()
    if row is None:
        return None
    if block_height is None or row.applied_height is None or row.applied_height <= block_height:
        return row.value
    return None


def _governance_executors(session: Session, chain_id: str, block_height: int | None = None) -> frozenset[str] | None:
    """Authorized GOVERNANCE_EXECUTE senders from the on-chain
    ``governance_executors`` chain parameter (comma-separated addresses).

    The parameter is chain state, applied identically on every node, so the
    gate is deterministic — a per-node env list would recreate the
    slash-authority class of silent divergence.

    Returns ``None`` when the parameter is unset or empty. The caller is
    FAIL-CLOSED on that result from block_version 5 upward — an unset list
    rejects GOVERNANCE_EXECUTE outright (the validate_transaction gate at
    ~line 1064); only pre-v5 sealed history is lenient, since executes
    mined before the parameter existed carry no authorization requirement.
    Once set, only listed senders pass validation on every node at the
    same height. ``block_height`` selects the value in force at that
    height — the sender gate applies to blocks of every version once set,
    so replay must see the height-scoped value.
    """
    value = _chain_parameter_value(session, chain_id, "governance_executors", block_height)
    if not value or not value.strip():
        return None
    return frozenset(_to_ait_address(a.strip()) for a in value.split(",") if a.strip())


def _bond_slash_authority(session: Session, chain_id: str, block_height: int | None = None) -> str | None:
    """Return the canonical bond-slash authority address.

    The on-chain ``bond_slash_authority`` chain parameter wins: it is applied
    identically on every node that imports the parameter-setting transaction,
    so the gate is deterministic across the fleet. ``BOND_SLASH_AUTHORITY_ADDRESS``
    remains the bootstrap for ``block_height=None`` callers only (mempool
    pre-checks, non-consensus introspection): for a known block height, chain
    history alone decides — an env value would make the answer depend on
    which records this node has applied so far. Heights below the first
    on-chain record resolve ``None`` — fail closed: a chain that never sealed
    the parameter has no determinable authority. A disagreement between env
    and the on-chain value is logged, because per-node env drift is exactly
    how the 1-2 Sep slashes were skipped on one fleet node.
    """
    onchain_value = _chain_parameter_value(session, chain_id, "bond_slash_authority", block_height)
    env_addr = os.getenv("BOND_SLASH_AUTHORITY_ADDRESS", "").strip()
    if onchain_value is not None:
        # A record at-or-below this height is authoritative — including an
        # empty value, which is a deliberate clear (unset): it must not fall
        # back to env.
        if onchain_value.strip():
            addr = canonical_address(onchain_value.strip())
            if env_addr and canonical_address(env_addr) != addr:
                logger.warning(
                    "BOND_SLASH_AUTHORITY_ADDRESS=%s disagrees with on-chain bond_slash_authority=%s; using the on-chain value",
                    env_addr,
                    addr,
                )
            return addr
        return None
    if block_height is None and env_addr:
        return canonical_address(env_addr)
    return None


def _validator_deactivation_authority(session: Session, chain_id: str, block_height: int | None = None) -> str | None:
    """Return the canonical validator-deactivation authority address (#1198).

    Same resolution contract as :func:`_bond_slash_authority`, but a dedicated
    parameter per the #1198 §5 ruling — activation power is deliberately not
    shared with the economic slash authority. On-chain
    ``validator_deactivation_authority`` wins at every known block height;
    ``VALIDATOR_DEACTIVATION_AUTHORITY_ADDRESS`` bootstraps only
    ``block_height=None`` (mempool pre-checks). Unset resolves ``None`` —
    fail closed.
    """
    onchain_value = _chain_parameter_value(session, chain_id, "validator_deactivation_authority", block_height)
    env_addr = os.getenv("VALIDATOR_DEACTIVATION_AUTHORITY_ADDRESS", "").strip()
    if onchain_value is not None:
        if onchain_value.strip():
            addr = canonical_address(onchain_value.strip())
            if env_addr and canonical_address(env_addr) != addr:
                logger.warning(
                    "VALIDATOR_DEACTIVATION_AUTHORITY_ADDRESS=%s disagrees with on-chain "
                    "validator_deactivation_authority=%s; using the on-chain value",
                    env_addr,
                    addr,
                )
            return addr
        return None
    if block_height is None and env_addr:
        return canonical_address(env_addr)
    return None


def _parse_validator_deactivation_payload(payload: dict[str, Any]) -> tuple[str, str, str] | str:
    """Validate and extract ``(validator_addr, evidence_hash, bond_id)`` or return a skip reason."""
    raw_address = payload.get("validator_address")
    if not raw_address:
        return "missing validator_address in payload"
    try:
        validator_addr = canonical_address(str(raw_address), strict=True)
    except ValueError:
        return "validator_address is not a strict 0x+40hex address"
    evidence_hash = str(payload.get("evidence_hash") or "").strip()
    if not evidence_hash:
        return "missing evidence_hash in payload"
    bond_id = payload.get("bond_id")
    if not bond_id:
        return "missing bond_id in payload"
    return (validator_addr, evidence_hash, str(bond_id))


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
        _bal, _nonce, escrow_exists = read_current_account(session, chain_id, _BOND_ESCROW_ADDRESS)
        escrow_balance = _bal if _bal is not None else 0
        escrow_missing = not escrow_exists
    else:
        escrow = session.get(Account, (chain_id, _BOND_ESCROW_ADDRESS))
        escrow_balance = escrow.balance if escrow is not None else 0
        escrow_missing = escrow is None
    if escrow_missing or escrow_balance < bond.amount:
        return f"escrow balance {escrow_balance} below release amount {bond.amount}"
    return None


def _escrow_address(job_id: str) -> str:
    """Derive a deterministic escrow address for a job (S-4).

    Funds locked for a job go to escrow:<job_id> — an address with no
    known private key, so the locked value is unspendable by the node
    wallet until a release or refund transaction moves it.
    """
    return canonical_address("0x" + keccak(f"aitbc.escrow.{job_id}".encode()).hex()[:40])


def _is_escrow_address(address: str, job_id: str | None = None) -> bool:
    """Check whether an address is (or matches) a per-escrow lock address."""
    if job_id is None:
        # Without a job_id, check if it matches the escrow prefix pattern.
        # This is a heuristic — we can't reverse the hash.
        return False
    return canonical_address(address) == _escrow_address(job_id)


def _is_valid_0x_address(address: str) -> bool:
    """Return True if ``address`` is a canonical 42-character 0x address."""
    try:
        normalized = canonical_address(address)
    except Exception:
        return False
    return normalized.startswith("0x") and len(normalized) == 42


def _escrow_settlement_authority(session: Session, chain_id: str, block_height: int | None = None) -> str | None:
    """Return the canonical settlement authority for v3+ escrow releases/refunds.

    The on-chain ``escrow_settlement_authority`` chain parameter wins: it is
    applied identically on every node, so the gate is deterministic — the
    per-node env value drifting is the same silent-divergence class as the
    1-2 Sep slashes skipped on one fleet node. ``settings.escrow_settlement_authority``
    / ``ESCROW_RELEASE_ADDRESS`` remain the bootstrap for
    ``block_height=None`` callers only: for a known block height, chain
    history alone decides. A disagreement between the two is logged. Returns
    None when nothing is configured — the caller decides whether that fails
    open (pre-v5 replay compat) or closed (v5+).
    """
    onchain_value = _chain_parameter_value(session, chain_id, "escrow_settlement_authority", block_height)
    env_addr = (settings.escrow_settlement_authority or os.getenv("ESCROW_RELEASE_ADDRESS", "")).strip()
    if onchain_value is not None:
        # A record at-or-below this height is authoritative — including an
        # empty value (a deliberate clear), which means unset.
        if onchain_value.strip():
            addr = canonical_address(onchain_value.strip())
            if env_addr and canonical_address(env_addr) != addr:
                logger.warning(
                    "escrow settlement authority env value %s disagrees with on-chain escrow_settlement_authority=%s; using the on-chain value",
                    env_addr,
                    addr,
                )
            return addr
        return None
    if block_height is None and env_addr:
        return canonical_address(env_addr)
    return None


def _bridge_release_authority(session: Session, chain_id: str, block_height: int | None = None) -> str | None:
    """Return the canonical authority for v5+ bridge credit signatures.

    The on-chain ``bridge_release_authority`` chain parameter wins (applied
    identically on every node); ``settings.bridge_release_authority`` /
    ``BRIDGE_RELEASE_AUTHORITY`` is the bootstrap for ``block_height=None``
    callers only — for a known block height, chain history alone decides.
    The escrow settlement authority is the transitional default — the bridge
    service signs credits with the same operator settlement key, so chains
    that configured only escrow still resolve deterministically. Returns
    None when nothing is configured — the caller decides whether that fails
    open (pre-v5 replay compat) or closed (v5+).
    """
    onchain_value = _chain_parameter_value(session, chain_id, "bridge_release_authority", block_height)
    env_addr = (settings.bridge_release_authority or os.getenv("BRIDGE_RELEASE_AUTHORITY", "")).strip()
    if onchain_value is not None:
        # A record at-or-below this height is authoritative — including an
        # empty value (a deliberate clear), which resolves the transitional
        # escrow default rather than a per-node env value.
        if onchain_value.strip():
            addr = canonical_address(onchain_value.strip())
            if env_addr and canonical_address(env_addr) != addr:
                logger.warning(
                    "bridge release authority env value %s disagrees with on-chain bridge_release_authority=%s; using the on-chain value",
                    env_addr,
                    addr,
                )
            return addr
        return _escrow_settlement_authority(session, chain_id, block_height)
    if block_height is None and env_addr:
        return canonical_address(env_addr)
    return _escrow_settlement_authority(session, chain_id, block_height)


def _escrow_fee_recipient(session: Session, chain_id: str, block_height: int | None = None) -> str | None:
    """Return the canonical fee recipient for v11+ ESCROW_FEE_SWEEP txs.

    The on-chain ``escrow_fee_recipient`` chain parameter wins (applied
    identically on every node); ``settings.escrow_fee_recipient`` /
    ``ESCROW_FEE_RECIPIENT`` is the bootstrap for ``block_height=None``
    callers only — for a known block height, chain history alone decides.
    A disagreement between the two is logged. Returns None when nothing is
    configured — the sweep fails closed: a fee that cannot be pinned to its
    governed recipient must not move.
    """
    onchain_value = _chain_parameter_value(session, chain_id, "escrow_fee_recipient", block_height)
    env_addr = (settings.escrow_fee_recipient or os.getenv("ESCROW_FEE_RECIPIENT", "")).strip()
    if onchain_value is not None:
        # A record at-or-below this height is authoritative — including an
        # empty value (a deliberate clear), which means unset.
        if onchain_value.strip():
            addr = canonical_address(onchain_value.strip())
            if env_addr and canonical_address(env_addr) != addr:
                logger.warning(
                    "escrow fee recipient env value %s disagrees with on-chain escrow_fee_recipient=%s; using the on-chain value",
                    env_addr,
                    addr,
                )
            return addr
        return None
    if block_height is None and env_addr:
        return canonical_address(env_addr)
    return None


def _escrow_fee_cap_bps(session: Session, chain_id: str, block_height: int | None = None) -> int:
    """v23 governed fee cap (basis points of a job's locked amount).

    The on-chain ``escrow_fee_cap_bps`` chain parameter wins; with no record the
    consensus default applies. A record that is not an integer in
    ``0..MAX_ESCROW_FEE_CAP_BPS`` fails closed to 0 (no allowance, plain residue
    rule) — the same on every node, because it depends on chain history only.
    """
    onchain_value = _chain_parameter_value(session, chain_id, "escrow_fee_cap_bps", block_height)
    if onchain_value is None:
        return DEFAULT_ESCROW_FEE_CAP_BPS
    try:
        bps = int(str(onchain_value).strip())
    except (TypeError, ValueError):
        return 0
    return bps if 0 <= bps <= MAX_ESCROW_FEE_CAP_BPS else 0


# The five authority chain parameters — each names the address(es) allowed to
# sign a class of chain-side actions. From v12 a GOVERNANCE_EXECUTE
# ``parameter_change`` to one of them is value-checked by
# ``_validate_authority_parameter_value``; other parameter names stay outside
# the gate (the forward-compat escape hatch — unknown actions and parameters
# keep today's lenient apply).
_AUTHORITY_PARAMETERS = frozenset(
    {
        "bond_slash_authority",
        "bridge_release_authority",
        "escrow_fee_recipient",
        "escrow_settlement_authority",
        "governance_executors",
        "validator_deactivation_authority",
    }
)

# All but governance_executors name exactly one address.
_SINGLE_ADDRESS_PARAMETERS = _AUTHORITY_PARAMETERS - {"governance_executors"}

# v12/A5 floor (operator decision, 2026-10-06): a governance_executors value is
# refused unless at least one listed member holds this balance at apply height —
# the minimum that can pay one fee, so a never-funded or all-typo'd executor list
# cannot seal a governance freeze. Consensus has no minimum fee (gap-era executes
# sealed with fee=0), so the floor is a baked constant, not the tx's fee. The a16
# ops tool enforces the stricter fee+headroom policy off-chain; the chain keeps
# the minimum.
_EXECUTOR_MIN_BALANCE_UNITS = DEFAULT_TX_FEE_UNITS

_ZERO_ADDRESS = "0x" + "00" * 20


def _validate_authority_parameter_value(
    session: Session, chain_id: str, parameter: str, value: Any, fee: int, *, block_version: int
) -> str | None:
    """v12 value check for a ``parameter_change`` to an authority parameter.

    Returns the rejection message — ``GOVERNANCE_EXECUTE rejected: <parameter>
    value <why>`` — or None when the value is acceptable. Callers handle the
    trigger: ``block_version >= 12``, action ``parameter_change`` (or absent,
    matching the apply default), and ``parameter`` in ``_AUTHORITY_PARAMETERS``.

    ``fee`` is the transaction fee. It is unused while the A5 floor is the
    baked ``_EXECUTOR_MIN_BALANCE_UNITS`` constant; it stays in the signature
    so a fee-relative floor could replace the constant without churning the
    call sites.
    """
    prefix = f"GOVERNANCE_EXECUTE rejected: {parameter} value"
    # ``value: null`` applies as a deliberate clear (""); validate the same
    # string apply would store so admission and apply cannot disagree.
    raw = "" if value is None else str(value)
    if not raw.strip():
        return f"{prefix} must not be empty"
    elements = [e.strip() for e in raw.split(",") if e.strip()]
    if not elements:
        return f"{prefix} must name at least one address"
    canonical = _canonical_authority_addresses(elements, prefix)
    if isinstance(canonical, str):
        return canonical
    shape_error = _authority_value_shape_error(parameter, canonical, prefix)
    if shape_error is not None:
        return shape_error
    if parameter == "governance_executors" and not _executors_funded(session, chain_id, canonical, block_version):
        return (
            f"{prefix} has no member holding the executor minimum "
            f"{_EXECUTOR_MIN_BALANCE_UNITS} units — an executor list that cannot pay a fee freezes governance"
        )
    return None


def _canonical_authority_addresses(elements: list[str], prefix: str) -> list[str] | str:
    """Canonicalize each comma element; error string on the first bad one."""
    canonical: list[str] = []
    for element in elements:
        try:
            canonical.append(canonical_address(element, strict=True))
        except ValueError:
            return f"{prefix} element {element!r:.60} is not a 0x + 40-hex address"
    return canonical


def _authority_value_shape_error(parameter: str, canonical: list[str], prefix: str) -> str | None:
    """Zero-address, duplicate, and arity checks shared by all authority params."""
    seen: set[str] = set()
    for address in canonical:
        if address == _ZERO_ADDRESS:
            return f"{prefix} element {address} is the zero address"
        if address in seen:
            return f"{prefix} repeats {address}"
        seen.add(address)
    if parameter in _SINGLE_ADDRESS_PARAMETERS and len(canonical) > 1:
        return f"{prefix} must name exactly one address, got {len(canonical)}"
    return None


def _executors_funded(session: Session, chain_id: str, canonical: list[str], block_version: int) -> bool:
    """True when at least one executor holds the minimum balance."""
    for address in canonical:
        if block_version >= 24 or v24_rules_is_active():
            # #1314 V2: scalar authoritative balance — bypasses
            # identity-map staleness for executor funding checks. The
            # version term covers admission callers outside the apply
            # contextvar; the contextvar covers in-apply callers.
            _bal, _nonce, _exists = read_current_account(session, chain_id, address)
            balance = _bal if _bal is not None else 0
        else:
            account = session.get(Account, (chain_id, address))
            balance = account.balance if account is not None else 0
        if balance >= _EXECUTOR_MIN_BALANCE_UNITS:
            return True
    return False


# v13: bound on the ``execution_payload`` a GOVERNANCE_PROPOSE commits to the
# chain. A parameter_change fits in a few hundred bytes; 16 KiB is generous
# headroom that still keeps a proposal from parking an unbounded blob in the
# canonical transaction table.
_V13_MAX_EXECUTION_PAYLOAD_BYTES = 16 * 1024


class _V13Verdict(NamedTuple):
    """A v13 binding failure: a short metric-safe reason token and the
    human-readable rejection message."""

    reason: str
    message: str


def _sealed_propose_execution_payload(
    session: Session, chain_id: str, proposal_id: str, before_height: int
) -> tuple[bool, Any]:
    """Return ``(found, execution_payload)`` of the GOVERNANCE_PROPOSE sealed for
    ``proposal_id`` in a block strictly below ``before_height``.

    The transaction table is canonical — every node holds the same sealed rows —
    so this resolves identically under replay on every node, unlike the
    node-local ``governance_proposal`` table (which is only populated on the
    host that served the create RPC and can never be a consensus input). The
    strict ``block_height <`` bound enforces the ordering rule: the PROPOSE must
    be sealed in an *earlier* block — an EXECUTE cannot bind a PROPOSE carried
    in the same block or a later one.
    """
    row = session.exec(
        select(Transaction)
        .where(
            Transaction.chain_id == chain_id,
            Transaction.type == "GOVERNANCE_PROPOSE",
            Transaction.payload.op("->>")("proposal_id") == proposal_id,  # type: ignore
            Transaction.block_height < before_height,  # type: ignore[operator]
        )
        .order_by(Transaction.block_height.desc())  # type: ignore[union-attr]
    ).first()
    if row is None:
        return (False, None)
    return (True, (row.payload or {}).get("execution_payload"))


def _sealed_execute_exists(session: Session, chain_id: str, proposal_id: str, before_height: int) -> bool:
    """True when a GOVERNANCE_EXECUTE naming ``proposal_id`` already sealed in
    a block strictly below ``before_height``. Canonical like the proposal
    lookup — the transaction table holds the same sealed rows on every node.
    The strict ``<`` bound keeps the current transaction's own row (if it is
    already flushed mid-apply) from rejecting itself."""
    return (
        session.exec(
            select(Transaction.id).where(
                Transaction.chain_id == chain_id,
                Transaction.type == "GOVERNANCE_EXECUTE",
                Transaction.payload.op("->>")("proposal_id") == proposal_id,  # type: ignore
                Transaction.block_height < before_height,  # type: ignore[operator]
            )
        ).first()
        is not None
    )


def _governance_propose_binding_verdict(payload: dict[str, Any]) -> _V13Verdict | None:
    """v13: a GOVERNANCE_PROPOSE must carry the ``execution_payload`` it commits
    to, as a dict within ``_V13_MAX_EXECUTION_PAYLOAD_BYTES``."""
    execution_payload = payload.get("execution_payload")
    if not isinstance(execution_payload, dict):
        return _V13Verdict(
            "propose_missing_execution_payload",
            "GOVERNANCE_PROPOSE rejected: an execution_payload object is required from v13",
        )
    if len(json.dumps(execution_payload, sort_keys=True, separators=(",", ":"))) > _V13_MAX_EXECUTION_PAYLOAD_BYTES:
        return _V13Verdict(
            "propose_execution_payload_oversized",
            f"GOVERNANCE_PROPOSE rejected: execution_payload exceeds {_V13_MAX_EXECUTION_PAYLOAD_BYTES} bytes",
        )
    return None


def _governance_execute_binding_verdict(
    session: Session, chain_id: str, payload: dict[str, Any], *, block_height: int | None
) -> _V13Verdict | None:
    """v13: a GOVERNANCE_EXECUTE must name a ``proposal_id`` whose GOVERNANCE_PROPOSE
    sealed in an earlier block, and its ``execution_payload`` must equal the
    stored one — the executor can only apply the payload the proposal committed
    to, not a swapped or fat-fingered substitute."""
    proposal_id = payload.get("proposal_id")
    if not proposal_id:
        return _V13Verdict(
            "execute_missing_proposal_id",
            "GOVERNANCE_EXECUTE rejected: proposal_id is required from v13",
        )
    if block_height is None:
        # The transaction would land in the next block — same convention as
        # mempool admission, which always passes a concrete height.
        head = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).first()
        block_height = (head or 0) + 1
    found, stored = _sealed_propose_execution_payload(session, chain_id, str(proposal_id), block_height)
    if not found:
        return _V13Verdict(
            "execute_unknown_proposal",
            f"GOVERNANCE_EXECUTE rejected: no GOVERNANCE_PROPOSE for proposal '{proposal_id}' sealed in an earlier block",
        )
    if stored != payload.get("execution_payload"):
        return _V13Verdict(
            "execute_payload_mismatch",
            f"GOVERNANCE_EXECUTE rejected: execution_payload does not match sealed proposal '{proposal_id}'",
        )
    if _sealed_execute_exists(session, chain_id, str(proposal_id), block_height):
        return _V13Verdict(
            "execute_already_executed",
            f"GOVERNANCE_EXECUTE rejected: proposal '{proposal_id}' already executed",
        )
    return None


def _governance_binding_verdict(
    session: Session,
    chain_id: str,
    tx_type: str,
    tx_payload: Any,
    *,
    block_height: int | None,
) -> _V13Verdict | None:
    """The v13 binding rules scored without the version gate — the shadow path
    (v13_would_reject_*) calls this on every GOVERNANCE_PROPOSE/EXECUTE so a
    would-reject surfaces as a metric before the rules are armed."""
    payload = tx_payload
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, RecursionError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if tx_type == "GOVERNANCE_PROPOSE":
        return _governance_propose_binding_verdict(payload)
    if tx_type == "GOVERNANCE_EXECUTE":
        return _governance_execute_binding_verdict(session, chain_id, payload, block_height=block_height)
    return None


def _governance_binding_error(
    session: Session,
    chain_id: str,
    tx_type: str,
    tx_payload: Any,
    *,
    block_version: int,
    block_height: int | None,
) -> str | None:
    """The v13 proposal-binding checks for GOVERNANCE_PROPOSE/EXECUTE (V-2).

    Shared by ``validate_transaction`` and mempool admission so the door refuses
    exactly what apply refuses. Below v13 — the default everywhere, since the
    ``state_transition_v13_height`` default is an unreachable sentinel — every
    check returns None and behaviour is byte-identical to today.
    """
    if block_version < 13:
        return None
    verdict = _governance_binding_verdict(session, chain_id, tx_type, tx_payload, block_height=block_height)
    return verdict.message if verdict else None


def _v13_shadow_observe(
    session: Session,
    chain_id: str,
    tx_type: str,
    tx_payload: Any,
    *,
    block_version: int,
    block_height: int | None,
    tx_hash: str = "",
) -> str | None:
    """Score the v13 binding rules on a transaction and count the result.

    Always increments ``v13_shadow_checked_*`` (the positive control). Below
    v13 a would-be rejection only counts ``v13_would_reject_<reason>`` and
    logs — never refuses; at or above the armed height the caller gets the
    rejection message (the real reject is counted too, same as v9).
    """
    if tx_type not in ("GOVERNANCE_PROPOSE", "GOVERNANCE_EXECUTE"):
        return None
    count_v13_shadow_checked(tx_type)
    verdict = _governance_binding_verdict(session, chain_id, tx_type, tx_payload, block_height=block_height)
    if verdict is None:
        return None
    count_v13_would_reject(verdict.reason)
    if block_version >= 13:
        return verdict.message
    logger.warning(
        "v13 shadow: %s tx %s would be rejected (%s)",
        tx_type,
        tx_hash,
        verdict.reason,
    )
    return None


def _authority_parameter_change_error(
    session: Session, chain_id: str, tx_payload: Any, fee: int, *, block_version: int
) -> str | None:
    """The v12 value check for a GOVERNANCE_EXECUTE payload, shared by apply
    validation and mempool admission so the door refuses exactly what apply
    refuses.

    Returns None below v12, for a non-dict payload or execution_payload, for
    actions other than ``parameter_change`` (an absent action defaults to it,
    matching apply), and for parameters outside ``_AUTHORITY_PARAMETERS``.
    """
    if block_version < 12:
        return None
    payload = tx_payload
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, RecursionError):
            payload = {}
    if not isinstance(payload, dict):
        return None
    execution_payload = payload.get("execution_payload")
    if not isinstance(execution_payload, dict):
        return None
    if execution_payload.get("action", "parameter_change") != "parameter_change":
        return None
    parameter = execution_payload.get("parameter")
    if parameter not in _AUTHORITY_PARAMETERS:
        return None
    return _validate_authority_parameter_value(
        session, chain_id, parameter, execution_payload.get("value"), fee, block_version=block_version
    )


def _get_escrow_lock(session: Session, chain_id: str, job_id: str) -> Transaction | None:
    """Find the on-chain ESCROW_LOCK transaction for ``job_id``."""
    return session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == "ESCROW_LOCK",
            Transaction.payload.op("->>")("job_id") == job_id,  # type: ignore
        )
    ).first()


def _get_escrow_lock_block_version(session: Session, chain_id: str, job_id: str) -> int | None:
    """Return the state-transition version of the block that mined the lock for ``job_id``."""
    lock_tx = _get_escrow_lock(session, chain_id, job_id)
    if not lock_tx or lock_tx.block_height is None:
        return None
    row = session.exec(
        # Column-only: the entity select would eager-load the block's selectin
        # transactions/receipts; only the recorded version stamp is needed.
        select(Block.height, Block.block_metadata).where(Block.chain_id == chain_id, Block.height == lock_tx.block_height)
    ).first()
    if row is None:
        return None
    return get_block_version({"block_metadata": row[1]}, row[0])


def _escrow_beneficiary(lock_tx: Transaction, tx_type: str) -> str | None:
    """Return the canonical address that ``tx_type`` must pay for this lock."""
    payload = lock_tx.payload or {}
    if tx_type == "ESCROW_RELEASE":
        provider = payload.get("provider") or ""
        return _to_ait_address(provider) if provider else None
    if tx_type == "ESCROW_REFUND":
        return _to_ait_address(lock_tx.sender or "")
    return None


_ESCROW_SETTLEMENT_TYPES = ("ESCROW_RELEASE", "ESCROW_REFUND")


def _escrow_lock_rows(session: Session, chain_id: str, job_id: str) -> list[Transaction]:
    """All applied ESCROW_LOCK rows for ``job_id``.

    Only ``status='confirmed'`` transactions moved funds — rejected
    write-backs and failed applies never did and must not count toward
    the obligation.
    """
    return list(
        session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                Transaction.type == "ESCROW_LOCK",
                Transaction.payload.op("->>")("job_id") == job_id,  # type: ignore
                Transaction.status == "confirmed",
            )
        )
    )


def _sum_confirmed_escrow_values(
    session: Session, chain_id: str, job_id: str, tx_types: tuple[str, ...], exclude_tx_hash: str = ""
) -> int | None:
    """Σ ``value`` of confirmed ``tx_types`` rows for ``job_id``; None when a row's
    value is missing/unparseable (the caller treats the state as unbounded)."""
    total = 0
    for tx in session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type.in_(tx_types),  # type: ignore
            Transaction.payload.op("->>")("job_id") == job_id,  # type: ignore
            Transaction.status == "confirmed",
        )
    ):
        if exclude_tx_hash and tx.tx_hash == exclude_tx_hash:
            continue
        try:
            total += int(tx.value)
        except (TypeError, ValueError):
            return None
    return total


def _escrow_obligation_state(
    session: Session, chain_id: str, job_id: str, exclude_tx_hash: str = "", fee_cap_bps: int | None = None
) -> dict[str, Any]:
    """v23 obligation accounting for one job's escrow custody.

    ``obligation`` = Σ sealed ``ESCROW_LOCK.value``;
    ``settled`` = Σ sealed ``ESCROW_RELEASE``/``ESCROW_REFUND``.value
    (``exclude_tx_hash`` lets a tx be revalidated without counting
    itself); ``remaining`` = obligation − settled is the most any single
    release/refund may still pay, and custody beyond it is sweep residue.

    A lock or settlement row whose ``value`` is missing/unparseable marks
    the state unbounded: ``remaining`` is ``None`` and callers must fail
    closed rather than under-count what is owed.

    With ``fee_cap_bps`` (sweep validation), the state also carries ``swept``
    (Σ sealed ``ESCROW_FEE_SWEEP``.value) and ``fee_allowance`` =
    ``obligation × fee_cap_bps / 10000 − swept`` (floored at 0), which is 0
    until some release/refund has settled (``settled > 0``): the authority
    cannot pull the fee out of a lock nothing has settled yet.
    """
    obligation = 0
    unbounded = False
    for lock in _escrow_lock_rows(session, chain_id, job_id):
        try:
            obligation += int(lock.value)
        except (TypeError, ValueError):
            unbounded = True
            break
    settled = 0
    swept = 0
    fee_allowance = 0
    if not unbounded:
        settled_sum = _sum_confirmed_escrow_values(session, chain_id, job_id, _ESCROW_SETTLEMENT_TYPES, exclude_tx_hash)
        unbounded = settled_sum is None
        settled = settled_sum or 0
    if fee_cap_bps is not None and not unbounded:
        swept_sum = _sum_confirmed_escrow_values(session, chain_id, job_id, ("ESCROW_FEE_SWEEP",), exclude_tx_hash)
        unbounded = swept_sum is None
        swept = swept_sum or 0
        if not unbounded and settled > 0:
            fee_allowance = max(0, obligation * fee_cap_bps // 10_000 - swept)
    return {
        "obligation": obligation,
        "settled": settled,
        "swept": swept,
        "fee_allowance": fee_allowance,
        "remaining": None if unbounded else obligation - settled,
        "unbounded": unbounded,
    }


def _escrow_lock_beneficiaries(session: Session, chain_id: str, job_id: str, tx_type: str) -> tuple[str | None, bool]:
    """v23 beneficiary resolution across ALL sealed locks for ``job_id``.

    ``ESCROW_RELEASE`` pays each lock's recorded ``provider``;
    ``ESCROW_REFUND`` pays each lock's ``sender``. Returns
    ``(beneficiary, ambiguous)`` — more than one distinct beneficiary, or
    a lock whose beneficiary field is missing, is ambiguous and the caller
    must refuse rather than guess.
    """
    seen: set[str] = set()
    for lock in _escrow_lock_rows(session, chain_id, job_id):
        if tx_type == "ESCROW_RELEASE":
            provider = (lock.payload or {}).get("provider") or ""
            addr = _to_ait_address(provider) if provider else None
        elif tx_type == "ESCROW_REFUND":
            addr = _to_ait_address(lock.sender or "") if lock.sender else None
        else:
            return None, True
        if not addr:
            return None, True
        seen.add(addr)
    if len(seen) == 1:
        return next(iter(seen)), False
    return (None, True) if seen else (None, False)


_ESCROW_CONTEXT_TYPES = ("ESCROW_RELEASE", "ESCROW_REFUND", "ESCROW_FEE_SWEEP")


def _escrow_tx_job_id(tx_data: dict[str, Any]) -> str:
    payload = tx_data.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return payload.get("job_id") or tx_data.get("job_id") or ""


def _escrow_v23_context_params(session: Session, chain_id: str, block_height: int | None) -> tuple[bool, int | None]:
    """v23 gate + fee cap for ``build_escrow_context`` — below v23 the
    context is bit-for-bit what it always was (no obligation fields)."""
    if block_height is None or get_block_version_for_height(block_height) < 23:
        return False, None
    return True, _escrow_fee_cap_bps(session, chain_id, block_height)


def _escrow_duplicate_settlement(tx_datas: list[dict[str, Any]]) -> bool:
    """v23 (R12-05-F1/#1232, R14-06-F1/#1230): two settlement txs for one job
    cannot share a single static ``remaining`` — the second must see the
    first's settlement — so such a batch falls back to sequential, which
    applies the checks in order."""
    settlement_counts: dict[str, int] = {}
    for tx_data in tx_datas:
        if _tx_type(tx_data) not in _ESCROW_CONTEXT_TYPES:
            continue
        job_id = _escrow_tx_job_id(tx_data)
        settlement_counts[job_id] = settlement_counts.get(job_id, 0) + 1
    return any(count > 1 for count in settlement_counts.values())


def _escrow_merge_existing_entry(
    session: Session,
    chain_id: str,
    tx_type: str,
    job_id: str,
    entry: dict[str, Any],
    resolved_fee_recipient: Callable[[], str | None],
) -> dict[str, Any] | None:
    """Fold a settlement tx into an existing context entry.

    Returns the (possibly mutated) entry to store, or ``None`` when the
    batch must go sequential so its own checks apply. An entry that already
    covers this tx is returned unchanged.
    """
    if entry.get("tx_type") == tx_type:
        return entry
    if tx_type == "ESCROW_FEE_SWEEP":
        # Release/refund + sweep for one job is the designed settlement
        # cadence: the sweep adds no beneficiary constraint, it only
        # needs the chain-level fee recipient on the entry.
        entry["fee_recipient"] = resolved_fee_recipient()
        return entry
    if entry.get("tx_type") == "ESCROW_FEE_SWEEP":
        # The sweep arrived first; this release/refund still needs its
        # lock fields resolved against the same entry.
        lock_tx = _get_escrow_lock(session, chain_id, job_id) if job_id else None
        if lock_tx is None:
            return None
        entry["tx_type"] = tx_type
        entry["lock_version"] = _get_escrow_lock_block_version(session, chain_id, job_id)
        entry["expected_beneficiary"] = _escrow_beneficiary(lock_tx, tx_type)
        return entry
    # A second release/refund for the same job with a different tx_type
    # would need a different beneficiary — an invalid batch anyway; let
    # the sequential path apply its own checks.
    return None


def _escrow_new_context_entry(
    session: Session,
    chain_id: str,
    tx_type: str,
    job_id: str,
    *,
    v23: bool,
    obligation_fields: Callable[[str], dict[str, Any]],
    resolved_authority: Callable[[], str | None],
    resolved_fee_recipient: Callable[[], str | None],
) -> dict[str, Any] | None:
    if tx_type == "ESCROW_FEE_SWEEP":
        entry: dict[str, Any] = {
            "tx_type": tx_type,
            "escrow_addr": _escrow_address(job_id) if job_id else "",
            "settlement_authority": resolved_authority(),
            "fee_recipient": resolved_fee_recipient(),
        }
        if v23:
            entry.update(obligation_fields(job_id))
        return entry
    lock_tx = _get_escrow_lock(session, chain_id, job_id) if job_id else None
    if lock_tx is None:
        return None
    if v23:
        # v23: beneficiary resolves across ALL sealed locks; ambiguity
        # sends the batch sequential where validate_transaction refuses
        # it identically.
        expected_beneficiary, beneficiary_ambiguous = _escrow_lock_beneficiaries(session, chain_id, job_id, tx_type)
        if beneficiary_ambiguous:
            return None
    else:
        expected_beneficiary = _escrow_beneficiary(lock_tx, tx_type)
    entry = {
        "tx_type": tx_type,
        "lock_version": _get_escrow_lock_block_version(session, chain_id, job_id),
        "expected_beneficiary": expected_beneficiary,
        "escrow_addr": _escrow_address(job_id),
        # The pure path has no DB access — every entry carries the
        # resolved chain-level values.
        "settlement_authority": resolved_authority(),
    }
    if v23:
        entry.update(obligation_fields(job_id))
    return entry


class _EscrowContextParams:
    """Per-batch lazy resolvers for ``build_escrow_context``.

    The chain-level parameters are not per-job — resolve them lazily on the
    first escrow tx so batches without one never pay for the queries.
    """

    def __init__(self, session: Session, chain_id: str, block_height: int | None, fee_cap_bps: int | None) -> None:
        self._session = session
        self._chain_id = chain_id
        self._block_height = block_height
        self._fee_cap_bps = fee_cap_bps
        self._authority: str | None = None
        self._authority_resolved = False
        self._fee_recipient: str | None = None
        self._fee_recipient_resolved = False
        self._obligation_cache: dict[str, dict[str, Any]] = {}

    def authority(self) -> str | None:
        if not self._authority_resolved:
            self._authority = _escrow_settlement_authority(self._session, self._chain_id, self._block_height)
            self._authority_resolved = True
        return self._authority

    def fee_recipient(self) -> str | None:
        if not self._fee_recipient_resolved:
            self._fee_recipient = _escrow_fee_recipient(self._session, self._chain_id, self._block_height)
            self._fee_recipient_resolved = True
        return self._fee_recipient

    def obligation_fields(self, job_id: str) -> dict[str, Any]:
        if job_id not in self._obligation_cache:
            self._obligation_cache[job_id] = _escrow_obligation_state(
                self._session, self._chain_id, job_id, fee_cap_bps=self._fee_cap_bps
            )
        state = self._obligation_cache[job_id]
        return {
            "remaining_obligation": state["remaining"],
            "obligation_unbounded": state["unbounded"],
            "fee_allowance": state["fee_allowance"],
        }


def build_escrow_context(
    session: Session, chain_id: str, tx_datas: list[dict[str, Any]], block_height: int | None = None
) -> dict[str, dict[str, Any]] | None:
    """Prefetch per-job metadata for ESCROW_RELEASE/ESCROW_REFUND/ESCROW_FEE_SWEEP txs (S-4, v11).

    The pure/parallel ``compute_state_delta`` cannot touch the DB, so callers
    that want parallel validation of v3+ blocks must supply this map:
    ``{job_id: {"lock_version": int|None, "expected_beneficiary": str|None,
    "escrow_addr": str, "settlement_authority": str|None,
    "fee_recipient": str|None}}``.
    ``settlement_authority``/``fee_recipient`` are chain-level (on-chain
    parameters, env fallback) rather than per-job, but every entry carries the
    resolved values so the pure path never needs a session.

    A sweep needs no lock: the custody account is derived from the job_id and a
    v2-era job simply holds no balance there. A release/refund plus a sweep for
    the same job in one batch is the designed settlement cadence, so a sweep
    merges into an existing entry instead of forcing the sequential path.

    Returns ``None`` when any release/refund references a job_id with no
    on-chain lock — the sequential path applies its own missing-lock rules, so
    the caller must keep sequential processing to stay consensus-identical.
    Batches with no escrow settlement txs return ``{}`` (cheap no-op).
    """
    context: dict[str, dict[str, Any]] = {}
    # v23 (R12-05-F1/#1232, R14-06-F1/#1230): each context entry carries the
    # job's obligation state so the pure path can enforce the bound without
    # a session. Two settlement txs for one job cannot share a single
    # static ``remaining`` — the second must see the first's settlement —
    # so such a batch falls back to sequential, which applies the checks
    # in order. Below v23 the context is bit-for-bit what it always was.
    v23, fee_cap_bps = _escrow_v23_context_params(session, chain_id, block_height)
    params = _EscrowContextParams(session, chain_id, block_height, fee_cap_bps)

    if v23 and _escrow_duplicate_settlement(tx_datas):
        return None

    for tx_data in tx_datas:
        tx_type = _tx_type(tx_data)
        if tx_type not in _ESCROW_CONTEXT_TYPES:
            continue
        job_id = _escrow_tx_job_id(tx_data)
        existing = context.get(job_id)
        if existing is not None:
            entry = _escrow_merge_existing_entry(session, chain_id, tx_type, job_id, existing, params.fee_recipient)
        else:
            entry = _escrow_new_context_entry(
                session,
                chain_id,
                tx_type,
                job_id,
                v23=v23,
                obligation_fields=params.obligation_fields,
                resolved_authority=params.authority,
                resolved_fee_recipient=params.fee_recipient,
            )
        if entry is None:
            return None
        context[job_id] = entry
    return context


def _refund_lock_record(session: Session, chain_id: str, lock_hash: str, exclude_tx_hash: str = "") -> dict[str, Any]:
    """Resolve the ``{exists, sender, amount, refunded}`` record for a refund's
    named lock — the shape ``validate_bridge_refund_lock`` consumes.

    ``refunded`` means another *sealed* ``BRIDGE_REFUND`` (``block_height`` set,
    hash different from ``exclude_tx_hash``) already names the same lock — so a
    legitimately sealed refund re-validates cleanly while a second refund for
    the same lock fails. ``exists`` requires the lock row to be sealed too.
    """
    lock = session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.tx_hash == lock_hash,
            Transaction.type == "BRIDGE_LOCK",
        )
    ).first()
    refunded = False
    for prior in session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == "BRIDGE_REFUND",
            Transaction.block_height.is_not(None),  # type: ignore[union-attr]
        )
    ):
        if exclude_tx_hash and prior.tx_hash == exclude_tx_hash:
            continue
        prior_payload = prior.payload if isinstance(prior.payload, dict) else {}
        if prior_payload.get("lock_tx_hash") == lock_hash:
            refunded = True
            break
    return {
        "exists": lock is not None and lock.block_height is not None,
        "sender": lock.sender if lock else None,
        "amount": lock.value if lock else None,
        "refunded": refunded,
    }


def build_bridge_lock_context(
    session: Session, chain_id: str, tx_datas: list[dict[str, Any]]
) -> dict[str, dict[str, Any]] | None:
    """Prefetch lock records for BRIDGE_REFUND txs (v6), like ``build_escrow_context``.

    Returns ``{lock_tx_hash: {"exists","sender","amount","refunded"}}`` for the
    pure path. Returns ``None`` when the batch is unsafe for parallel
    resolution — two refunds naming the same lock — so the caller falls back to
    the sequential path, which applies the double-refund rule in order.
    Batches with no refunds return ``{}`` (cheap no-op).
    """
    context: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for tx_data in tx_datas:
        if _tx_type(tx_data) != "BRIDGE_REFUND":
            continue
        lock_hash = bridge_refund_lock_hash(tx_data)
        if lock_hash in seen:
            return None
        seen.add(lock_hash)
        if lock_hash and lock_hash not in context:
            context[lock_hash] = _refund_lock_record(session, chain_id, lock_hash)
    return context


def _ensure_account(session: Session, chain_id: str, address: str) -> Account:
    ait_addr = _to_ait_address(address)
    account = session.get(Account, (chain_id, ait_addr))
    if not account:
        account = Account(chain_id=chain_id, address=ait_addr, balance=0, nonce=0)
        session.add(account)
        session.flush()
    return account


def _tx_type(tx_data: dict[str, Any], tx_record: Transaction | None = None) -> str:
    """Resolve the canonical transaction type from record or tx data."""
    if tx_record and tx_record.type:
        return tx_record.type.upper()
    tx_type = tx_data.get("type", "TRANSFER")
    if not tx_type or tx_type == "TRANSFER":
        payload = tx_data.get("payload", {})
        if isinstance(payload, dict):
            tx_type = payload.get("type", "TRANSFER")
    # str() coercion: a non-string type (e.g. payload.type=123) must not raise —
    # the pure path resolves the same shape via str().upper(), and an
    # AttributeError here is a proposer-stalling crash, not a rejection.
    return str(tx_type or "TRANSFER").upper()


def get_recorded_block_version(block_data_or_block: dict[str, Any] | object) -> int | None:
    """Return the version stamped in ``block_metadata``, or ``None``.

    ``None`` covers both an absent ``state_transition_version`` key and
    malformed/unparseable metadata.
    """
    metadata: Any = None
    if isinstance(block_data_or_block, dict):
        metadata = block_data_or_block.get("block_metadata")
    else:
        metadata = getattr(block_data_or_block, "block_metadata", None)
    if not metadata:
        return None
    try:
        parsed = metadata if isinstance(metadata, dict) else json.loads(metadata)
        version = parsed.get("state_transition_version")
        if version is not None:
            return int(version)
    except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
        pass
    return None


def get_block_version(block_data_or_block: dict[str, Any] | object, height: int = 0) -> int:
    """Return the state-transition rule version that should be used for a block.

    Below the v8 activation height a recorded ``state_transition_version`` in
    ``block_metadata`` wins, and unversioned blocks fall back to the configured
    activation heights so historical blocks replay under the rules that
    produced them.

    At or above v8 the stamp is advisory only: the height-derived version
    always applies. ``block_metadata`` is covered by neither the block hash
    nor the proposer's signature, so trusting the stamp would let any relay
    pick the rules a block is validated under; ignoring it removes the
    dependency on the unauthenticated field entirely. A recorded version that
    disagrees with the height — or is absent — is logged and counted, never
    obeyed.
    """
    recorded = get_recorded_block_version(block_data_or_block)
    v8_threshold = getattr(settings, "state_transition_v8_height", 0)
    if v8_threshold > 0 and height >= v8_threshold:
        expected = get_block_version_for_height(height)
        if recorded != expected:
            metrics_registry.increment("block_version_stamp_mismatch_total")
            logger.warning(
                "Block at height %s records state_transition_version=%s; height requires %s — using the height-derived version",
                height,
                recorded,
                expected,
            )
        return expected
    if recorded is not None:
        return recorded
    v7_threshold = getattr(settings, "state_transition_v7_height", 0)
    if v7_threshold > 0 and height >= v7_threshold:
        return 7
    v6_threshold = getattr(settings, "state_transition_v6_height", 0)
    if v6_threshold > 0 and height >= v6_threshold:
        return 6
    v5_threshold = getattr(settings, "state_transition_v5_height", 0)
    if v5_threshold > 0 and height >= v5_threshold:
        return 5
    v4_threshold = getattr(settings, "state_transition_v4_height", 0)
    if v4_threshold > 0 and height >= v4_threshold:
        return 4
    v3_threshold = getattr(settings, "state_transition_v3_height", 0)
    if v3_threshold > 0 and height >= v3_threshold:
        return 3
    v2_threshold = getattr(settings, "state_transition_v2_height", 0)
    if v2_threshold > 0 and height >= v2_threshold:
        return 2
    return 1


def get_block_version_for_height(height: int) -> int:
    """Return the state-transition rule version a *new* block at ``height`` should use.

    Unlike ``get_block_version``, this does not inspect an existing block's
    metadata. It is used by the proposer to determine which version to stamp into
    the block it is about to build.
    """
    # v9+ thresholds treat any configured value as active; v3-v8 additionally
    # require a positive threshold (their getattr default is 0). v2 inverts:
    # heights *below* its threshold run v1 rules.
    for version in range(25, 2, -1):
        threshold = getattr(settings, f"state_transition_v{version}_height", None)
        if not threshold:
            continue
        if version >= 9:
            if height >= threshold:
                return version
        elif threshold > 0 and height >= threshold:
            return version
    v2_threshold = getattr(settings, "state_transition_v2_height", 0)
    if v2_threshold > 0 and height < v2_threshold:
        return 1
    return 2


def use_account_nonce_override(tx_data: dict[str, Any], block_version: int) -> bool:
    """Whether apply-time code must substitute the account's live nonce for the
    tx's recorded nonce before validation.

    Two cases require the substitution:

    - ``block_version < 7``: the parallel-proposal era could seal same-sender
      tx pairs sharing one stored nonce — the second only applied because the
      producer rewrote the nonce to the live account value. Re-importing those
      blocks needs the same rewrite or historical replay diverges.
    - Unsigned internal transactions (preregistered MESSAGE/bridge rows,
      operator-relayed records) carry no signed nonce to enforce; the check
      must not run on a meaningless stored value.

    For signed transactions at v7+ the envelope nonce is authoritative: the
    signature covers it, and the nonce check enforces it for real instead of
    being a tautology behind the rewrite.
    """
    if block_version < 7:
        return True
    return not (tx_data.get("signature") or tx_data.get("sig"))


# Address fields the staking RPCs put the authorized party under: consensus
# staking signs {"address": ...}; agent staking is operator-signed with the
# user under "user_address" (or "staker_address").
_AUTH_ADDRESS_FIELDS = ("address", "user_address", "staker_address", "creator_address")


def _payload_auth_named_addresses(message: dict[str, Any]) -> set[str]:
    """Return the normalized addresses the signed message names."""
    named: set[str] = set()
    for field in _AUTH_ADDRESS_FIELDS:
        raw = message.get(field)
        if not raw:
            continue
        try:
            named.add(_to_ait_address(str(raw)))
        except (TypeError, ValueError):
            continue
    return named


def _payload_auth_binds_transfer(tx_type: str, message: dict[str, Any], tx_data: dict[str, Any]) -> bool:
    """Check that a verified auth message names the transfer it authorizes.

    All deterministic context binding lives here so a captured signature
    cannot be re-attached to a different transfer:

    - party: the message must name the account a ``STAKE_LOCK`` debits or the
      account a ``STAKE_RELEASE`` credits (the release sender is the keyless
      escrow, so the payee is the authorized party).
    - chain: a message carrying ``chain_id`` must match the tx's chain.
    - action: a message carrying ``action`` must match the transfer type, so
      a "stake" signature cannot ride a release.
    - amount: a lock's message amount must equal the transferred value.
    - stake: a release's message ``stake_id`` must equal the payload's
      ``stake_id``/``agent_stake_id``; for locks the field is optional (the
      consensus-staking row id is assigned after signing) but must match
      when both sides carry it.
    - bounty: ``BOUNTY_LOCK`` binds the creator and ``reward_amount``;
      ``BOUNTY_REFUND`` binds the refunded payee; ``BOUNTY_PAYOUT`` is
      operator-signed and the payee is resolved server-side, so it binds
      ``submission_id`` instead. ``bounty_id`` must match whenever the
      signed message carries it.
    """
    role = _payload_auth_role(tx_type)
    if role is None:
        return False
    party, expected_action = role
    if not _payload_auth_party_binds(party, message, tx_data):
        return False
    if not _payload_auth_chain_action_binds(message, tx_data, expected_action):
        return False
    if not _payload_auth_amount_binds(tx_type, message, tx_data):
        return False
    return _payload_auth_ids_binds(tx_type, message, tx_data.get("payload") or {})


def _payload_auth_role(tx_type: str) -> tuple[str | None, str] | None:
    """(party field, expected action) for the transfer type, or None."""
    if tx_type in ("STAKE_LOCK", "BOUNTY_LOCK"):
        return ("from", "stake")
    if tx_type in ("STAKE_RELEASE", "BOUNTY_REFUND"):
        return ("to", "unstake")
    if tx_type == "BOUNTY_PAYOUT":
        # operator-signed; the payee is resolved server-side
        return (None, "")
    return None


def _payload_auth_party_binds(party_field: str | None, message: dict[str, Any], tx_data: dict[str, Any]) -> bool:
    """The message must name the account the transfer debits/credits."""
    if party_field is None:
        return True
    party = tx_data.get(party_field)
    if not party:
        return True  # absent party field skips the binding, as before
    try:
        bound_party = _to_ait_address(str(party))
    except (TypeError, ValueError):
        return False
    return bound_party in _payload_auth_named_addresses(message)


def _payload_auth_chain_action_binds(message: dict[str, Any], tx_data: dict[str, Any], expected_action: str) -> bool:
    """A message's chain_id/action, when present, must match the transfer."""
    if message.get("chain_id") is not None and str(message.get("chain_id")) != str(tx_data.get("chain_id")):
        return False
    return "action" not in message or message.get("action") == expected_action


def _payload_auth_amount_binds(tx_type: str, message: dict[str, Any], tx_data: dict[str, Any]) -> bool:
    """A lock's signed amount must equal the transferred value."""
    if tx_type not in ("STAKE_LOCK", "BOUNTY_LOCK"):
        return True
    amount = message.get("amount", message.get("additional_amount", message.get("reward_amount")))
    value = tx_data.get("value", tx_data.get("amount", 0))
    try:
        return amount is not None and int(amount) == int(value)
    except (TypeError, ValueError):
        return False


def _payload_auth_ids_binds(tx_type: str, message: dict[str, Any], payload: dict[str, Any]) -> bool:
    """stake_id / bounty_id / submission_id / lock_tx_hashes cross-checks."""
    msg_stake = message.get("stake_id")
    tx_stake = payload.get("stake_id") or payload.get("agent_stake_id")
    if tx_type == "STAKE_RELEASE":
        if msg_stake is None or tx_stake is None or str(msg_stake) != str(tx_stake):
            return False
    elif msg_stake is not None and tx_stake is not None and str(msg_stake) != str(tx_stake):
        return False
    msg_bounty = message.get("bounty_id")
    tx_bounty = payload.get("bounty_id")
    if tx_type == "BOUNTY_LOCK":
        if msg_bounty is None or tx_bounty is None or str(msg_bounty) != str(tx_bounty):
            return False
    elif msg_bounty is not None and tx_bounty is not None and str(msg_bounty) != str(tx_bounty):
        return False
    if tx_type == "BOUNTY_PAYOUT":
        msg_sub = message.get("submission_id")
        tx_sub = payload.get("submission_id")
        if msg_sub is None or tx_sub is None or str(msg_sub) != str(tx_sub):
            return False
    return _payload_auth_lock_hashes_binds(message, payload)


def _payload_auth_lock_hashes_binds(message: dict[str, Any], payload: dict[str, Any]) -> bool:
    """lock_tx_hashes bind only when the signed message names them — the
    user-staking route signs them, operator-signed agent releases predate the
    field and must not break."""
    msg_locks = message.get("lock_tx_hashes")
    tx_locks = payload.get("lock_tx_hashes")
    if msg_locks is not None and tx_locks is not None:
        if sorted(str(h) for h in msg_locks) != sorted(str(h) for h in tx_locks):
            return False
    return True


# Blocks per day at the chain's fixed 60s cadence — deterministic across nodes,
# unlike wall-clock timestamps which the proposer controls.
_STAKE_LOCK_BLOCKS_PER_DAY = 1440


def _validate_stake_release_locks(
    session: Session,
    chain_id: str,
    tx_data: dict[str, Any],
    tx_hash: str,
    value: int,
    recipient_addr: str,
) -> tuple[bool, str]:
    """v4 consensus check: a STAKE_RELEASE must fully reference matured locks.

    ``payload.lock_tx_hashes`` names the confirmed STAKE_LOCK transactions this
    release spends. Every lock must exist, belong to the payee, and — when it
    declares ``lock_days`` — have been sealed for at least that many days at the
    fixed 60s block cadence. Locks with no ``lock_days`` (legacy, agent stakes,
    auto-stake top-ups) are treated as matured. The claimed lock set must not
    overlap any already-sealed release, and the summed principal must cover the
    release value.
    """
    claimed = _claimed_lock_hashes(tx_data, tx_hash)
    if isinstance(claimed, str):
        return (False, claimed)

    locks = _load_claimed_locks(session, chain_id, claimed, recipient_addr, tx_hash, value)
    if isinstance(locks, str):
        return (False, locks)

    matured = _claimed_locks_matured(session, chain_id, locks, value, tx_hash)
    if isinstance(matured, str):
        return (False, matured)

    return _claimed_locks_unspent(session, chain_id, claimed, tx_hash)


def _claimed_lock_hashes(tx_data: dict[str, Any], tx_hash: str) -> set[str] | str:
    """Normalize + validate ``payload.lock_tx_hashes``; error string on failure."""
    payload = tx_data.get("payload") or {}
    raw_hashes = payload.get("lock_tx_hashes")
    if not isinstance(raw_hashes, list) or not raw_hashes or not all(isinstance(h, str) and h for h in raw_hashes):
        return f"STAKE_RELEASE {tx_hash} payload must carry a non-empty lock_tx_hashes list"
    claimed = {h.lower() for h in raw_hashes}
    if len(claimed) != len(raw_hashes):
        return f"STAKE_RELEASE {tx_hash} lock_tx_hashes contains duplicates"
    return claimed


def _load_claimed_locks(
    session: Session,
    chain_id: str,
    claimed: set[str],
    recipient_addr: str,
    tx_hash: str,
    value: int,
) -> list[Transaction] | str:
    """Fetch each claimed lock; verify existence, payee, and principal coverage."""
    locks: list[Transaction] = []
    for h in claimed:
        lock = session.exec(
            select(Transaction).where(
                Transaction.chain_id == chain_id,
                func.lower(Transaction.tx_hash) == h,
                Transaction.type == "STAKE_LOCK",
                Transaction.block_height.is_not(None),  # type: ignore[union-attr]
            )
        ).first()
        if lock is None:
            return f"STAKE_RELEASE {tx_hash} references unknown or unconfirmed lock {h}"
        if _to_ait_address(lock.sender or "") != recipient_addr:
            return f"STAKE_RELEASE {tx_hash} lock {h} belongs to {lock.sender}, not payee {recipient_addr}"
        locks.append(lock)

    locked_total = sum(int(lock.value or 0) for lock in locks)
    if locked_total < value:
        return f"STAKE_RELEASE {tx_hash} value {value} exceeds locked principal {locked_total}"
    return locks


def _claimed_locks_matured(
    session: Session,
    chain_id: str,
    locks: list[Transaction],
    value: int,
    tx_hash: str,
) -> str | None:
    """Verify every ``lock_days`` window has elapsed at the next block height."""
    parent_height = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).one()
    next_height = (parent_height or 0) + 1
    for lock in locks:
        lock_payload = lock.payload or {}
        lock_days = lock_payload.get("lock_days")
        if lock_days in (None, 0):
            continue  # legacy / agent / auto-stake locks carry no window
        try:
            unlock_height = int(lock.block_height or 0) + int(str(lock_days)) * _STAKE_LOCK_BLOCKS_PER_DAY
        except (TypeError, ValueError):
            return f"STAKE_RELEASE {tx_hash} lock {lock.tx_hash} has invalid lock_days"
        if next_height < unlock_height:
            return f"STAKE_RELEASE {tx_hash} lock {lock.tx_hash} matures at height {unlock_height}, current {next_height}"
    return None


def _claimed_locks_unspent(
    session: Session,
    chain_id: str,
    claimed: set[str],
    tx_hash: str,
) -> tuple[bool, str]:
    """A lock may be spent only once: no sealed release may name any claimed hash."""
    # Pending same-block duplicates are a mempool-policy concern (mempool drops
    # them); only confirmed history is consensus state.
    for prior in session.exec(
        select(Transaction).where(
            Transaction.chain_id == chain_id,
            Transaction.type == "STAKE_RELEASE",
            Transaction.block_height.is_not(None),  # type: ignore[union-attr]
            Transaction.tx_hash != tx_hash,
        )
    ).all():
        prior_hashes = (prior.payload or {}).get("lock_tx_hashes") or []
        if claimed & {str(h).lower() for h in prior_hashes}:
            return (False, f"STAKE_RELEASE {tx_hash} lock already released by {prior.tx_hash}")
    return (True, "")


def _governance_execute_payload(tx_data: dict[str, Any], tx_hash: str) -> dict[str, Any] | None:
    """Normalize the tx payload (JSON string or dict); None when unusable."""
    payload = tx_data.get("payload", {}) or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            logger.warning("GOVERNANCE_EXECUTE payload is not valid JSON: %s", payload)
            return None
    return payload


class _TxValidationCtx:
    """Shared state threaded through ``validate_transaction``'s ordered checks.

    Each ``_vt_*`` validator runs in the exact position its source block held
    in the original monolith; the first non-None return is the verdict, so
    first-failure-wins error precedence is preserved block-for-block.
    """

    __slots__ = (
        "session",
        "chain_id",
        "tx_data",
        "tx_hash",
        "block_version",
        "block_height",
        "block_time",
        "skip_dedup",
        "tx_record",
        "tx_type",
        "sender_addr",
        "recipient_addr",
        "value",
        "fee",
        "sender_nonce",
        "sender_balance",
        "total_cost",
        "job_id",
        "lock_tx",
        "lock_version",
        "payload",
        "escrow_balance",
    )

    def __init__(
        self,
        *,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int,
        block_height: int | None,
        block_time: datetime | None,
        skip_dedup: bool,
    ) -> None:
        self.session = session
        self.chain_id = chain_id
        self.tx_data = tx_data
        self.tx_hash = tx_hash
        self.block_version = block_version
        self.block_height = block_height
        self.block_time = block_time
        self.skip_dedup = skip_dedup
        self.tx_record: Any = None
        self.tx_type: str = ""
        self.sender_addr: str = ""
        self.recipient_addr: str = ""
        self.value: Any = 0
        self.fee: Any = 0
        self.sender_nonce: int = 0
        self.sender_balance: Any = 0
        self.total_cost: Any = 0
        self.job_id: str = ""
        self.lock_tx: Any = None
        self.lock_version: Any = 0
        self.payload: Any = {}
        self.escrow_balance: Any = 0


from .state_transition_apply import _ApplyMixin
from .state_transition_handlers import _HandlerMixin
from .state_transition_validation import _ValidationMixin


class StateTransition(_ValidationMixin, _ApplyMixin, _HandlerMixin):
    """
    Validates and applies state transitions only through validated transactions.

    This class ensures that balance changes can only occur through properly
    validated transactions, preventing direct database manipulation of account
    balances.
    """

    def __init__(self) -> None:
        self._processed_nonces: dict[str, int] = {}
        self._processed_tx_hashes: set[str] = set()

    def reset_processed_cache(self) -> None:
        """Clear in-memory per-process tx/nonce caches.

        The caches are intended to prevent the same transaction from being
        applied twice within one block. Because a rejected block is rolled back,
        leaving the cache populated causes false "replay attack" errors on the
        next import attempt. Call this at the start of each block.
        """
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()

    def validate_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int = 2,
        block_height: int | None = None,
        *,
        skip_dedup: bool = False,
        block_time: datetime | None = None,
    ) -> tuple[bool, str]:
        """
        Validate a transaction before applying state changes.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash
            block_height: Height of the block carrying this transaction.
                Authority chain parameters resolve to the value in force at
                this height, so replayed blocks validate against the
                parameters as they were when the block was sealed. None
                resolves the current value (e.g. mempool pre-checks).

        Returns:
            Tuple of (is_valid, error_message)
        """
        ctx = _TxValidationCtx(
            session=session,
            chain_id=chain_id,
            tx_data=tx_data,
            tx_hash=tx_hash,
            block_version=block_version,
            block_height=block_height,
            block_time=block_time,
            skip_dedup=skip_dedup,
        )
        for _check in (
            self._vt_chain_id,
            self._vt_dedup,
            self._vt_prepare,
            self._vt_liquidity,
            self._vt_bridge_credit,
            self._vt_bridge_lock_sig,
            self._vt_bridge_lock_account,
            self._vt_bridge_withdraw,
            self._vt_escrow_lock_v3,
            self._vt_signature,
            self._vt_v9_signature,
            self._vt_stake_payload_auth,
            self._vt_sender_account,
            self._vt_nonce,
            self._vt_governance_execute,
            self._vt_governance_propose,
            self._vt_stake_release_locks,
            self._vt_zero_value_cost,
            self._vt_escrow_release_refund_job,
            self._vt_escrow_beneficiary,
            self._vt_escrow_obligation,
            self._vt_escrow_authority,
            self._vt_escrow_funding,
            self._vt_sweep_params,
            self._vt_sweep_fee_recipient,
            self._vt_sweep_custody,
            self._vt_sweep_obligation,
            self._vt_sweep_fee,
            self._vt_sender_balance,
            self._vt_receipt_claim,
            self._vt_ipfs_subscription,
            self._vt_gpu_register_fields,
            self._vt_gpu_register_ownership,
            self._vt_gpu_deregister,
            self._vt_gpu_allocate,
            self._vt_retired_gpu,
            self._vt_bond_lock_v20,
            self._vt_bond_lock_v19,
            self._vt_bond_v22,
            self._vt_agent_spend,
        ):
            verdict = _check(ctx)
            if verdict is not None:
                return verdict
        return (True, "Transaction validated successfully")

    def _vt_signature(self, ctx: _TxValidationCtx) -> tuple[bool, str] | None:
        signature = ctx.tx_data.get("signature")
        if signature and ctx.sender_addr:
            if not verify_transaction_signature(ctx.tx_data, signature, ctx.sender_addr):
                return (False, f"Invalid signature for transaction {ctx.tx_hash}")
        return None

    def apply_transaction(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int = 2,
        block_height: int | None = None,
        *,
        block_time: datetime | None = None,
        skip_dedup: bool = False,
    ) -> tuple[bool, str]:
        """
        Apply a validated transaction to update state.

        Args:
            session: Database session
            chain_id: Chain identifier
            tx_data: Transaction data
            tx_hash: Transaction hash
            block_version: State-transition rule version active for the block
                that contains this transaction. v1 keeps pre-2026-09-01 rules
                (no auto-created recipient/provider accounts); v2 applies the
                current account-creation rules.
            block_height: Height of the block carrying this transaction.
                Authority chain parameters resolve to the value in force at
                this height, and a parameter_change applied here takes effect
                from this height onward — replayed history can never fail
                because a parameter was set later in the chain.
            block_time: Sealed block-header timestamp. At block_version >= 18
                the volatile apply paths (liquidity stake ids/locked_until/
                accrual, bond locked_until/verdict) derive from it instead of
                wall-clock ``datetime.now(UTC)`` — the apply output is then a
                pure function of (transaction, prior state, block header).
                ``None`` keeps the volatile fallback for pre-v18 replay and
                non-consensus callers.

        Returns:
            Tuple of (success, error_message)
        """
        logger.info("apply_transaction called for tx %s, tx_data keys: %s", tx_hash, list(tx_data.keys()))
        is_valid, error_msg = self.validate_transaction(
            session,
            chain_id,
            tx_data,
            tx_hash,
            block_version=block_version,
            block_height=block_height,
            skip_dedup=skip_dedup,
            block_time=block_time,
        )
        if not is_valid:
            return (False, error_msg)
        sender_addr = _to_ait_address(tx_data.get("from") or "")
        if block_version >= 22 and sender_addr and tx_data.get("from") not in {"bridge_release", "bridge_refund"}:
            # v22 R1 (CONSENSUS-STATE-001): validation passed, so the sender
            # materializes now — the same committed row the pre-v22 importer
            # pre-create produced, but only on the success path. A rejected
            # tx never reaches this line and leaves no phantom account.
            _ensure_account(session, chain_id, sender_addr)
        recipient_addr = _to_ait_address(tx_data.get("to") or "")
        tx_record = session.exec(
            select(Transaction).where(Transaction.chain_id == chain_id, Transaction.tx_hash == tx_hash)
        ).first()
        tx_type = _tx_type(tx_data, tx_record)
        value = tx_data.get("value", 0)
        fee = tx_data.get("fee", 0)
        # Guard against BigInt overflow (SQLite INTEGER is 64-bit signed)
        _MAX_INT64 = 2**63 - 1
        if value < 0 or fee < 0 or value > _MAX_INT64 or fee > _MAX_INT64:
            raise ValueError(f"Transaction value/fee out of range: value={value}, fee={fee}")
        special = self._apply_special_transfer(
            session,
            chain_id,
            tx_data,
            tx_hash,
            tx_type,
            sender_addr,
            recipient_addr,
            value,
            fee,
            block_version=block_version,
            block_time=block_time,
        )
        if special is not None:
            return special
        sender_account, recipient_addr = self._apply_core_transfer(
            session, chain_id, tx_data, tx_type, sender_addr, recipient_addr, value, fee, block_version
        )
        side = self._apply_post_transfer_effects(
            session,
            chain_id,
            tx_data,
            tx_hash,
            tx_type,
            sender_addr,
            recipient_addr,
            value,
            sender_account,
            block_height,
            block_version=block_version,
            block_time=block_time,
        )
        if side is not None:
            return side
        return self._apply_success_epilogue(
            session,
            chain_id,
            tx_hash,
            tx_type,
            sender_addr,
            recipient_addr,
            sender_account,
            value,
            fee,
            block_version=block_version,
        )

    def apply_transaction_guarded(
        self,
        session: Session,
        chain_id: str,
        tx_data: dict[str, Any],
        tx_hash: str,
        block_version: int,
        **kwargs: Any,
    ) -> tuple[bool, str]:
        """``apply_transaction`` bracketed in a per-tx savepoint at v22+.

        CONSENSUS-STATE-001 (R1): at ``block_version >= 22`` a transaction
        whose apply returns ``False`` — or raises — must leave zero
        mutation. Validation-pass account materialization and any handler
        residue are rolled back to the savepoint, so importer, proposer,
        reapply and golden-engine callers all commit identical state for
        failed txs. Below v22 the call delegates unchanged: historical
        replay keeps whatever residue the original code committed.
        ``block_version`` is a required keyword so a caller cannot
        silently bypass the guard by omitting it.
        """
        if block_version < 22:
            return self.apply_transaction(session, chain_id, tx_data, tx_hash, block_version=block_version, **kwargs)
        if not session.in_transaction():
            # Anchor a real outer transaction first so begin_nested() creates a
            # genuine SAVEPOINT rather than auto-beginning the outer
            # transaction itself.
            session.begin()
        savepoint = session.begin_nested()
        try:
            if block_version >= 24:
                # #1314 R1: identity-map invalidation after raw-SQL writes is
                # active for the duration of this transaction's apply.
                with v24_rules_active():
                    result = self.apply_transaction(session, chain_id, tx_data, tx_hash, block_version=block_version, **kwargs)
            else:
                result = self.apply_transaction(session, chain_id, tx_data, tx_hash, block_version=block_version, **kwargs)
        except Exception:
            savepoint.rollback()
            raise
        if not result[0]:
            # Dispatch-failure: roll back to the savepoint. SessionTransaction.
            # rollback() restores the session snapshot (expunging ORM objects
            # added inside) as well as the DB writes, so no sender row or
            # handler residue survives — while the caller still owns the
            # outer transaction and records the deterministic failed-tx row.
            savepoint.rollback()
        # On success the savepoint is deliberately left open: calling
        # SessionTransaction.commit() here released the SAVEPOINT but the
        # writes then survived a later session.rollback() under the pysqlite
        # driver — effectively committing past the caller's transaction
        # boundary (verified empirically; breaks proposer PBFT-failure
        # rollback). An open savepoint costs nothing: later txs nest inside
        # it, a later failure rolls back only to its own savepoint, and the
        # caller's outer commit/rollback covers everything uniformly.
        return result

    def _bond_release_payout(
        self, session: Session, chain_id: str, sender_addr: str, release_amount: int, tx_hash: str
    ) -> str | None:
        escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
        sender = session.get(Account, (chain_id, sender_addr))
        if escrow and sender:
            session.refresh(escrow)
            session.refresh(sender)
            if escrow.balance < release_amount:
                return f"escrow balance {escrow.balance} below release amount {release_amount}"
            escrow.balance -= release_amount
            sender.balance += release_amount
            logger.info("BOND_RELEASE %s moved %s from escrow to %s", tx_hash, release_amount, sender_addr)
        return None

    def _bond_slash_move(self, session: Session, chain_id: str, slash_amount: int, tx_hash: str) -> str | None:
        escrow = _ensure_account(session, chain_id, _BOND_ESCROW_ADDRESS)
        burn = _ensure_account(session, chain_id, _BOND_BURN_ADDRESS)
        if escrow and burn:
            session.refresh(escrow)
            session.refresh(burn)
            if escrow.balance < slash_amount:
                return f"escrow balance {escrow.balance} below slash amount {slash_amount}"
            escrow.balance -= slash_amount
            burn.balance += slash_amount
            logger.info("BOND_SLASH %s moved %s from escrow to burn", tx_hash, slash_amount)
        return None

    def validate_state_transition(
        self, session: Session, chain_id: str, old_accounts: dict[str, Account], new_accounts: dict[str, Account]
    ) -> tuple[bool, str]:
        """
        Validate that state changes only occur through transactions.

        Args:
            session: Database session
            chain_id: Chain identifier
            old_accounts: Previous account state
            new_accounts: New account state

        Returns:
            Tuple of (is_valid, error_message)
        """
        for address, old_acc in old_accounts.items():
            if address not in new_accounts:
                continue
            new_acc = new_accounts[address]
            if old_acc.balance != new_acc.balance:
                logger.warning(
                    "Balance change detected for %s: %s -> %s (validated through transaction processing)",
                    address,
                    old_acc.balance,
                    new_acc.balance,
                )
        return (True, "State transition validated")

    def get_processed_nonces(self) -> dict[str, int]:
        """Get the last processed nonce for each address."""
        return self._processed_nonces.copy()

    def reset(self) -> None:
        """Reset the state transition validator (for testing)."""
        self._processed_nonces.clear()
        self._processed_tx_hashes.clear()


_state_transition = StateTransition()


def get_state_transition() -> StateTransition:
    """Get the global state transition instance."""
    return _state_transition
