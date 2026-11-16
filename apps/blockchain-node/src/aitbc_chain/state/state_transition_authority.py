"""Chain-parameter and transaction-authority resolution for ``StateTransition``.

Pure-move split out of ``state_transition.py``: the state-transition facade
re-exports every name defined here, so ``from aitbc_chain.state.state_transition
import X`` keeps working unchanged for all of them.

Import ``aitbc_chain.state.state_transition`` first (it wires this module in);
this module is not meant to be imported directly.
"""

from __future__ import annotations

import json
import os
from typing import Any, NamedTuple

from sqlalchemy import func
from sqlmodel import Session, select

from ..base_models import Block, ChainParameter, ChainParameterHistory, _to_ait_address
from ..config import settings
from ..logger import get_logger
from ..models import Account, Transaction
from ..v24_rules import v24_rules_is_active
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.utils.units import DEFAULT_TX_FEE_UNITS
from . import state_transition as _st
from .pure_state_transition import DEFAULT_ESCROW_FEE_CAP_BPS, MAX_ESCROW_FEE_CAP_BPS
from .v13_policy import count_v13_shadow_checked, count_v13_would_reject

# Keep the historical logger name: these helpers moved out of
# state_transition.py but their log records must stay identical.
logger = get_logger("aitbc_chain.state.state_transition")


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
            _bal, _nonce, _exists = _st.read_current_account(session, chain_id, address)
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


def _governance_execute_payload(tx_data: dict[str, Any], tx_hash: str) -> dict[str, Any] | None:
    """Normalize the tx payload (JSON string or dict); None when unusable."""
    payload = tx_data.get("payload", {}) or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            logger.warning("GOVERNANCE_EXECUTE payload is not valid JSON: %s", payload)
            return None
    return payload
