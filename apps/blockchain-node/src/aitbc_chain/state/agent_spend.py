"""v21 agent spend session enforcement (AGENT-SPEND-B-1, #1142).

Phase B of the agent-spend plan (docs/account-abstraction/implementation-plan.md):
validators agree on the spent budget on chain, so a compromised coordinator or
wallet daemon cannot push an over-cap spend through apply even if every
off-chain gate is bypassed.

Model (Phase A `AgentSpendSession` parity, chain-side):

- ``AGENT_SESSION_GRANT`` — owner-signed, zero-value tx carrying
  ``payload = {session_id, agent_address, daily_cap, ops, agent_id?,
  expires_at_height?}``. The signer *is* the session owner (``owner_address =
  sender``): there is no separate owner field to forge. ``session_id`` is
  unique per chain and never reusable — a spent or revoked id cannot be
  resurrected by re-grant.
- ``AGENT_SESSION_REVOKE`` — sets ``revoked_height``. Signer must be the
  session's ``owner_address`` *or* its ``agent_address``: the agent can always
  unbind itself, which is the mitigation for a squatter front-running a grant
  onto a victim address (the victim revokes and is free; a grant it never
  revokes is one it tolerates).
- A sender is **session-bound** while ≥1 session for its address is unrevoked.
  Every ``TRANSFER``/``ESCROW_LOCK`` it then signs must name
  ``payload.session_id``; a bound sender without one is refused at validate
  and at mempool admission.
- A named session must exist, be unrevoked, name the sender as
  ``agent_address``, be unexpired (``expires_at_height > block_height``), and
  list the op the tx type needs: ``TRANSFER`` → ``wallet.execute`` or
  ``transfer.approved``; ``ESCROW_LOCK`` → ``escrow.fund``. Naming a session
  on a spend by a different sender is refused — session_id is never an
  unauthenticated label.
- **Daily cap**: ``day = block_height // SPEND_DAY_BLOCKS`` (the 1290-block
  "day" the governance timelock already uses — deterministic from height, no
  wall clock in consensus). ``agent_spend_ledger.spent`` accumulates the tx
  ``value`` only; ``spent + value > daily_cap`` refuses. The charge lands in
  the same apply transaction as the balance debit, so the cap is atomic.

Determinism: every check reads only apply-written tables
(``agent_spend_session``/``agent_spend_ledger`` — both in the v21 committed
fingerprint set) and fields of the sealed tx/block. Nothing consults
``agent_identity`` (node-local RPC writer), wall clock, or env. Below v21 the
whole module is inert: ``AGENT_SESSION_*`` are just unknown type names and
replay as generic transfers exactly as before.

Not in scope (plan): arbitrary contract calls, EVM authorization lists.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from ..base_models import AgentSpendLedger, AgentSpendSession

if TYPE_CHECKING:
    from sqlmodel import Session

AGENT_SESSION_GRANT = "AGENT_SESSION_GRANT"
AGENT_SESSION_REVOKE = "AGENT_SESSION_REVOKE"
AGENT_SESSION_TX_TYPES: frozenset[str] = frozenset({AGENT_SESSION_GRANT, AGENT_SESSION_REVOKE})

# Tx types whose `value` counts against a session's daily cap. First B slice
# per the plan: native TRANSFER plus the escrow-funding type only.
SPEND_GATED_TX_TYPES: frozenset[str] = frozenset({"TRANSFER", "ESCROW_LOCK"})

# Same vocabulary as coordinator `spend_policy` (kept in sync deliberately —
# the two packages cannot import each other). `wallet.execute` is the generic
# spend op; `escrow.fund` the escrow-funding op; `transfer.approved` an
# owner-approved single transfer.
SESSION_OP_WALLET_EXECUTE = "wallet.execute"
SESSION_OP_ESCROW_FUND = "escrow.fund"
SESSION_OP_TRANSFER_APPROVED = "transfer.approved"
ALLOWED_SESSION_OPS: frozenset[str] = frozenset(
    {SESSION_OP_WALLET_EXECUTE, SESSION_OP_ESCROW_FUND, SESSION_OP_TRANSFER_APPROVED}
)

# Ops that satisfy a gated spend: TRANSFER accepts the generic or the
# approved-transfer op; ESCROW_LOCK must explicitly allow escrow funding.
_REQUIRED_OPS: dict[str, frozenset[str]] = {
    "TRANSFER": frozenset({SESSION_OP_WALLET_EXECUTE, SESSION_OP_TRANSFER_APPROVED}),
    "ESCROW_LOCK": frozenset({SESSION_OP_ESCROW_FUND}),
}

# One chain "day" in blocks — the bc-2 governance timelock's own day constant
# (1290 blocks ≈ 24 h at ~67 s/block).
SPEND_DAY_BLOCKS = 1290

_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_MAX_INT64 = 2**63 - 1
_MAX_SESSION_ID_LEN = 128
_MAX_AGENT_ID_LEN = 128


def spend_day(block_height: int) -> int:
    """Day bucket for a height: ``block_height // SPEND_DAY_BLOCKS``."""
    return block_height // SPEND_DAY_BLOCKS


def _payload_dict(tx_data: dict[str, Any] | None) -> dict[str, Any]:
    payload = (tx_data or {}).get("payload")
    return payload if isinstance(payload, dict) else {}


def _canonical_evm(value: Any) -> str | None:
    """Canonical 0x address or None — grants must name a well-formed address,
    not merely let the lenient canonicalizer pass a garbage string through."""
    if not isinstance(value, str) or not _EVM_ADDRESS_RE.match(value):
        return None
    from ..base_models import _to_ait_address

    return _to_ait_address(value)


def _get_session(session: Session, chain_id: str, session_id: Any) -> AgentSpendSession | None:
    if not isinstance(session_id, str) or not session_id:
        return None
    return session.get(AgentSpendSession, (chain_id, session_id))


def bound_agent_addresses(session: Session, chain_id: str, senders: set[str]) -> set[str]:
    """The subset of ``senders`` (already canonicalized) currently session-bound."""
    if not senders:
        return set()
    rows = session.exec(
        select(AgentSpendSession.agent_address).where(
            AgentSpendSession.chain_id == chain_id,
            AgentSpendSession.agent_address.in_(senders),  # type: ignore[attr-defined]
            AgentSpendSession.revoked_height.is_(None),  # type: ignore[union-attr]
        )
    ).all()
    return set(rows)


def _grant_payload_verdict(payload: dict[str, Any], block_height: int | None) -> str | None:
    """Shape checks on the grant payload — everything except the duplicate-id
    lookup (that one needs the DB)."""
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id or len(session_id) > _MAX_SESSION_ID_LEN:
        return "AGENT_SESSION_GRANT refused: session_id must be a non-empty string <= 128 chars"
    if _canonical_evm(payload.get("agent_address")) is None:
        return "AGENT_SESSION_GRANT refused: agent_address must be a 0x address"
    agent_id = payload.get("agent_id", "")
    if not isinstance(agent_id, str) or len(agent_id) > _MAX_AGENT_ID_LEN:
        return "AGENT_SESSION_GRANT refused: agent_id must be a string <= 128 chars"
    raw_cap: Any = payload.get("daily_cap")
    try:
        daily_cap = int(raw_cap)
    except (TypeError, ValueError, OverflowError):
        return "AGENT_SESSION_GRANT refused: daily_cap must be an integer"
    if not 0 < daily_cap <= _MAX_INT64:
        return "AGENT_SESSION_GRANT refused: daily_cap out of range"
    ops = payload.get("ops")
    if not isinstance(ops, list) or not ops or any(op not in ALLOWED_SESSION_OPS for op in ops):
        return "AGENT_SESSION_GRANT refused: ops must be a non-empty list of known spend ops"
    expires = payload.get("expires_at_height")
    if expires is not None:
        try:
            expires = int(expires)
        except (TypeError, ValueError, OverflowError):
            return "AGENT_SESSION_GRANT refused: expires_at_height must be an integer height"
        if block_height is not None and expires <= block_height:
            return "AGENT_SESSION_GRANT refused: expires_at_height is not in the future"
    return None


def _grant_verdict(
    session: Session,
    chain_id: str,
    sender: str,
    payload: dict[str, Any],
    block_height: int | None,
) -> str | None:
    shape_error = _grant_payload_verdict(payload, block_height)
    if shape_error:
        return shape_error
    session_id = payload["session_id"]
    if _get_session(session, chain_id, session_id) is not None:
        return f"AGENT_SESSION_GRANT refused: session {session_id} already exists"
    return None


def _revoke_verdict(
    session: Session,
    chain_id: str,
    sender: str,
    payload: dict[str, Any],
) -> str | None:
    row = _get_session(session, chain_id, payload.get("session_id"))
    if row is None:
        return "AGENT_SESSION_REVOKE refused: session not found"
    # Owner or the agent itself may revoke — the agent-side escape keeps a
    # squatter grant from locking the victim's spends.
    if sender not in (row.owner_address, row.agent_address):
        return "AGENT_SESSION_REVOKE refused: signer is not the session owner or agent"
    return None


def _spend_verdict(
    session: Session,
    chain_id: str,
    sender: str,
    tx_type: str,
    payload: dict[str, Any],
    value: int,
    block_height: int,
) -> str | None:
    session_id = payload.get("session_id")
    if session_id is None:
        if bound_agent_addresses(session, chain_id, {sender}):
            return f"{tx_type} refused: sender is session-bound — payload.session_id required"
        return None
    row = _get_session(session, chain_id, session_id)
    if row is None:
        return f"{tx_type} refused: agent spend session not found"
    if row.agent_address != sender:
        return f"{tx_type} refused: session agent does not match sender"
    if row.revoked_height is not None:
        return f"{tx_type} refused: spend session revoked"
    if row.expires_at_height is not None and block_height >= row.expires_at_height:
        return f"{tx_type} refused: spend session expired at height {row.expires_at_height}"
    required = _REQUIRED_OPS.get(tx_type) or frozenset()
    if required.isdisjoint(set(row.ops or [])):
        return f"{tx_type} refused: session does not allow this operation"
    if value < 0:
        return f"{tx_type} refused: negative value"
    ledger = session.get(AgentSpendLedger, (chain_id, row.session_id, spend_day(block_height)))
    spent = ledger.spent if ledger is not None else 0
    if value > row.daily_cap or spent + value > row.daily_cap:
        return f"{tx_type} refused: agent spend daily cap exceeded"
    return None


def agent_spend_verdict(
    session: Session,
    chain_id: str,
    sender: str,
    tx_type: str,
    payload: dict[str, Any] | None,
    value: Any,
    block_height: int | None,
) -> str | None:
    """v21 policy verdict for one transaction, or None when it may proceed.

    Read-only: mempool admission and apply-time validation share it, so it
    must never write — the ledger charge lives in ``charge_agent_spend``.
    ``block_height=None`` (non-consensus callers) skips enforcement entirely:
    the gate cannot be evaluated without the height it is anchored to.
    """
    if block_height is None:
        return None
    payload = payload if isinstance(payload, dict) else {}
    if tx_type == AGENT_SESSION_GRANT:
        return _grant_verdict(session, chain_id, sender, payload, block_height)
    if tx_type == AGENT_SESSION_REVOKE:
        return _revoke_verdict(session, chain_id, sender, payload)
    if tx_type in SPEND_GATED_TX_TYPES:
        try:
            spend_value = int(value or 0)
        except (TypeError, ValueError, OverflowError):
            spend_value = 0
        return _spend_verdict(session, chain_id, sender, tx_type, payload, spend_value, block_height)
    return None


def apply_agent_session_tx(
    session: Session,
    chain_id: str,
    tx_type: str,
    payload: dict[str, Any],
    sender: str,
    block_height: int | None,
) -> None:
    """Write the session-row effect of a validated GRANT/REVOKE (v21+, apply only)."""
    height = block_height if block_height is not None else 0
    if tx_type == AGENT_SESSION_GRANT:
        session.add(
            AgentSpendSession(
                chain_id=chain_id,
                session_id=payload["session_id"],
                agent_id=payload.get("agent_id") or "",
                agent_address=_canonical_evm(payload.get("agent_address")) or "",
                owner_address=sender,
                daily_cap=int(payload["daily_cap"]),
                ops=[str(op) for op in payload.get("ops") or []],
                expires_at_height=(
                    int(payload["expires_at_height"]) if payload.get("expires_at_height") is not None else None
                ),
                revoked_height=None,
                created_height=height,
            )
        )
        return
    if tx_type == AGENT_SESSION_REVOKE:
        row = _get_session(session, chain_id, payload.get("session_id"))
        if row is not None and row.revoked_height is None:
            row.revoked_height = height
            session.add(row)


def charge_agent_spend(
    session: Session,
    chain_id: str,
    tx_type: str,
    payload: dict[str, Any] | None,
    value: Any,
    block_height: int | None,
) -> None:
    """Apply-only ledger charge for a validated gated spend (v21+).

    Runs inside the same database transaction as the sender's balance debit,
    so the daily cap is atomic with the spend. A no-op for non-gated types and
    spends that named no session — validation already guaranteed that a named
    session exists and fits.
    """
    if block_height is None or tx_type not in SPEND_GATED_TX_TYPES:
        return
    payload = payload if isinstance(payload, dict) else {}
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    day = spend_day(block_height)
    ledger = session.get(AgentSpendLedger, (chain_id, session_id, day))
    try:
        spend_value = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        spend_value = 0
    if ledger is None:
        session.add(
            AgentSpendLedger(
                chain_id=chain_id,
                session_id=session_id,
                day=day,
                spent=spend_value,
                last_height=block_height,
            )
        )
    else:
        ledger.spent = ledger.spent + spend_value
        ledger.last_height = block_height
        session.add(ledger)


# Parallel-apply note: both block-level parallel paths (poa proposer and
# sync_block_import) are hard-bounded to ``2 <= block_version <= 8`` — a v21
# block can never reach ``compute_state_delta``. ``AGENT_SESSION_*`` are also
# in SEQUENTIAL_ONLY_TX_TYPES so direct per-tx callers force the sequential
# fallback. No dynamic pre-filter is needed while the v8 upper bound holds;
# if a future version widens the parallel window it must first audit the
# session/ledger side-table writes the delta map cannot model.
