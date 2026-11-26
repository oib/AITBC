"""Agent-economy staking RPC (V23-42). Distinct from consensus /rpc/staking/stake."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request
from sqlmodel import Session, func, select

from aitbc.rate_limiting import rate_limit

from ..base_models import AgentStakeMemo, AgentStakeRecord, _to_ait_address
from ..config import settings
from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Block
from ..protocol_escrow import (
    confirmed_lock_txs,
    protocol_transfer_pending,
    protocol_transfers_active,
    queue_protocol_transfer,
    stake_escrow_address,
)
from ..state.state_transition import _STAKE_LOCK_BLOCKS_PER_DAY
from .agent_economics_auth import (
    operator_address,
    payload_hash,
    require_int,
    require_operator_signature,
    require_signed_transfer_values,
)
from .retired import raise_for_unarmed
from .utils import _require_supported_chain, get_chain_id, validate_chain_id

_logger = get_logger(__name__)
MAX_LOCK_DAYS = 3650


def _account(session: Session, chain_id: str, address: str) -> Account:
    account = session.get(Account, (chain_id, address))
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {address} not found")
    return account


def _agent_lock_in_flight(session: Session, chain_id: str, stake_id: str, owner: str) -> str | None:
    """``"sealed"``/``"pending"``/``None`` for a STAKE_LOCK on this stake (#2628).

    ``agent_stake_id`` is caller-chosen and only unique per node (#3025): a
    foreign staker's lock under a colliding id must not count as this
    stake's — scope both halves to locks ``owner`` actually sent.
    """
    if confirmed_lock_txs(session, chain_id, "STAKE_LOCK", "agent_stake_id", stake_id, sender=owner):
        return "sealed"
    if protocol_transfer_pending(
        session,
        chain_id,
        "STAKE_LOCK",
        {"agent_stake_id": str(stake_id)},
        tx_match={"from": _to_ait_address(str(owner))},
    ):
        return "pending"
    return None


def _get_stake(session: Session, chain_id: str, stake_id: str) -> AgentStakeRecord | None:
    return session.exec(
        select(AgentStakeRecord).where(AgentStakeRecord.chain_id == chain_id, AgentStakeRecord.stake_id == stake_id)
    ).first()


def _canonical_status(session: Session, chain_id: str, stake_id: str, owner: str | None = None) -> tuple[str | None, str]:
    """Status derived from sealed history first, the local row second (#719).

    Sealed protocol transfers outrank the node-local ``agent_stake`` row —
    a stale row cannot mask a sealed STAKE_UNBOND/STAKE_RELEASE marker,
    and a host with no row at all answers from sealed txs instead of
    404-blind. Precedence: RELEASE > UNBOND > local row > LOCK.

    ``agent_stake_id`` is only unique per node (#3025): when ``owner`` (the
    staker address) is known, STAKE_LOCK claims scope by ``sender`` and
    STAKE_RELEASE by ``recipient`` — a foreign staker's colliding markers
    cannot fake this stake's status. STAKE_UNBOND is an escrow→escrow
    self-marker carrying no owner field, so it stays unscoped (its only
    effect is the unbonding transition, which unbond/complete still gate on
    staker_address + maturity).
    """
    if confirmed_lock_txs(session, chain_id, "STAKE_RELEASE", "agent_stake_id", stake_id, recipient=owner):
        return "completed", "chain"
    if confirmed_lock_txs(session, chain_id, "STAKE_UNBOND", "agent_stake_id", stake_id):
        return "unbonding", "chain"
    record = _get_stake(session, chain_id, stake_id)
    if record is not None:
        return record.status, "local"
    if confirmed_lock_txs(session, chain_id, "STAKE_LOCK", "agent_stake_id", stake_id, sender=owner):
        return "active", "chain"
    return None, "none"


def _resync_stake_to_unbonding(session: Session, chain_id: str, record: AgentStakeRecord) -> None:
    """#2360: bring a stale local row up to the sealed STAKE_UNBOND marker.

    Sealed history is authoritative (#719): when the marker is confirmed the
    stake IS unbonding regardless of what the node-local row says. The row
    is repaired in place — ``unbonding_at`` is taken from the sealed marker
    tx so the record reflects when the transition actually happened — and
    committed immediately so the repair survives a later refusal in the same
    request.
    """
    # STAKE_UNBOND is an escrow→escrow self-marker with no owner field on
    # the envelope or payload — a foreign staker's colliding marker cannot
    # be scoped out here (#3025 residual; see _canonical_status docstring).
    unbond_txs = confirmed_lock_txs(session, chain_id, "STAKE_UNBOND", "agent_stake_id", record.stake_id)
    unbonding_at = min((tx.created_at for tx in unbond_txs if tx.created_at is not None), default=None)
    now = datetime.now(UTC)
    record.status = "unbonding"
    record.unbonding_at = unbonding_at or now
    record.updated_at = now
    session.add(record)
    session.commit()


def _resync_stake_to_completed(session: Session, chain_id: str, record: AgentStakeRecord) -> None:
    """#2645: a sealed STAKE_RELEASE outranks a row stranded in ``unbonding``.

    The pre-#2628 ordering could seal the release while the row never
    flipped; the canonical guard then answers idempotent forever while the
    node-local row keeps reporting a stale status to anything reading it
    directly. Repair in place — there is no ``completed_at`` column, so
    ``updated_at`` carries the heal timestamp.
    """
    record.status = "completed"
    record.updated_at = datetime.now(UTC)
    session.add(record)
    session.commit()


_STAKE_STATUS_ORDER = {"active": 0, "unbonding": 1, "completed": 2}


def _heal_row_to_canonical(session: Session, chain_id: str, record: AgentStakeRecord, canonical: str) -> None:
    """#2645: repair a local row that is strictly behind sealed history.

    Only forward heals — a row ahead of the sealed markers (release queued
    but not yet sealed) must never be resynced backwards (#2360).
    """
    if _STAKE_STATUS_ORDER.get(canonical, -1) <= _STAKE_STATUS_ORDER.get(record.status, -1):
        return
    if canonical == "unbonding":
        _resync_stake_to_unbonding(session, chain_id, record)
    elif canonical == "completed":
        _resync_stake_to_completed(session, chain_id, record)


def _canonical_guard(
    session: Session, chain_id: str, stake_id: str, action: str, owner: str | None = None
) -> dict[str, Any] | None:
    """#748: a stale local row must not mutate under a newer sealed status.

    Called on the existing-row path: when sealed markers say the stake
    already transitioned, answer idempotent (the request effectively
    landed) or refuse 409 — never let a stale row emit a doomed marker.
    Returns None to proceed when the local row agrees with history.
    ``owner`` scopes the sealed-marker reads to this staker (#3025).
    """
    status, source = _canonical_status(session, chain_id, stake_id, owner=owner)
    if source != "chain":
        return None
    expected = {"unbond": "unbonding", "complete": "completed"}.get(action)
    if status is not None and status == expected:
        record = _get_stake(session, chain_id, stake_id)
        if record is not None:
            _heal_row_to_canonical(session, chain_id, record, status)
        return {"success": True, "idempotent": True, "stake_id": stake_id, "status": status, "source": source}
    # A sealed marker that is the action's required predecessor is not a
    # conflict when the local row agrees — complete after a sealed
    # STAKE_UNBOND must reach the normal path so a height-mature
    # STAKE_RELEASE can emit (#2336).
    if status == {"complete": "unbonding"}.get(action):
        record = _get_stake(session, chain_id, stake_id)
        if record is not None:
            if record.status == "completed":
                # Local is ahead of sealed history: either the STAKE_RELEASE
                # marker is still in the mempool — answer idempotent, a
                # re-run must neither emit a second release nor resync the
                # row backwards — or it was rejected/dropped after the row
                # flipped (#3010). Only a live pending marker earns the
                # idempotent answer; a dead one resyncs the row to the
                # sealed unbonding truth so the normal path re-drives the
                # release instead of stranding the principal.
                release_owner = owner or record.staker_address
                if protocol_transfer_pending(
                    session,
                    chain_id,
                    "STAKE_RELEASE",
                    {"agent_stake_id": str(stake_id)},
                    tx_match={"to": _to_ait_address(str(release_owner))},
                ):
                    return {
                        "success": True,
                        "idempotent": True,
                        "stake_id": stake_id,
                        "status": "completed",
                        "source": "local",
                    }
                _resync_stake_to_unbonding(session, chain_id, record)
                return None
            if record.status != status:
                # #2360: sealed STAKE_UNBOND is authoritative — a local row
                # left stale (e.g. the store was rebuilt from an older
                # snapshot) must not 409 a matured complete forever.
                # Re-sync the row to the sealed transition and let the
                # normal path evaluate maturity and emit STAKE_RELEASE.
                _resync_stake_to_unbonding(session, chain_id, record)
            return None
    if status in {"unbonding", "completed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Stake {stake_id} is {status} on sealed history — cannot {action} a stale local record",
        )
    return None


def _no_local_record(session: Session, chain_id: str, stake_id: str, action: str, owner: str | None = None) -> dict[str, Any]:
    """Missing-record answer for unbond/complete (#719): answer from sealed
    history instead of 404-blind. Idempotent when the sealed status already
    matches or passes the requested transition; 409 when the transition can
    only run on the host that served the lock. ``owner`` scopes the sealed
    reads to the requesting staker so a foreign colliding stake's markers
    cannot answer for it (#3025)."""
    status, source = _canonical_status(session, chain_id, stake_id, owner=owner)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
    idempotent_for = {"unbond": {"unbonding", "completed"}, "complete": {"completed"}}[action]
    if status in idempotent_for:
        return {"success": True, "idempotent": True, "stake_id": stake_id, "status": status, "source": source}
    raise HTTPException(
        status_code=409,
        detail=(
            f"Stake {stake_id} is {status} on sealed history but has no local record on this "
            f"host — {action} on the host that served its lock"
        ),
    )


@rate_limit(rate=20, per=60)
def get_agent_stake_status(request: Request, stake_id: str, chain_id: str | None = None) -> dict[str, Any]:
    """Canonical status: sealed STAKE_UNBOND/STAKE_RELEASE markers first,
    node-local record otherwise — a host with no row answers from sealed
    history rather than 404-blind (#719)."""
    cid = get_chain_id(chain_id)
    with session_scope() as session:
        status, source = _canonical_status(session, cid, stake_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
        return {"stake_id": stake_id, "status": status, "source": source}


def _signed_stake_id_matches(payload: dict[str, Any], stake_id: str) -> None:
    """The auth embedded in the emitted tx is the signed body; if it names a
    different stake than the path, the release would fail the v17 binding at
    seal time after the record was already mutated. Refuse up front."""
    signed = payload.get("stake_id")
    if signed is None or str(signed) != str(stake_id):
        raise HTTPException(status_code=400, detail="signed stake_id does not match the path stake_id")


@rate_limit(rate=20, per=60)
def create_agent_stake(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    if not validate_chain_id(chain_id):
        raise HTTPException(status_code=400, detail=f"Unsupported chain_id: {chain_id}")
    stake_id = payload.get("stake_id")
    staker = payload.get("user_address") or payload.get("staker_address")
    agent_wallet = payload.get("agent_wallet")
    if not stake_id or not staker or not agent_wallet:
        raise HTTPException(status_code=400, detail="stake_id, user_address and agent_wallet are required")
    staker = _to_ait_address(str(staker))
    agent_wallet = _to_ait_address(str(agent_wallet))
    amount = require_int(payload, "amount")
    lock_period = require_int(payload, "lock_period", minimum=1)
    if lock_period > MAX_LOCK_DAYS:
        raise HTTPException(status_code=400, detail=f"lock_period must be <= {MAX_LOCK_DAYS}")

    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Agent staking (stake)")
        existing = _get_stake(session, chain_id, str(stake_id))
        if existing:
            # #2641: idempotent only for the SAME request — a replay that
            # names another staker, agent wallet, amount or term must not
            # answer success over a stake it did not create.
            if (
                existing.staker_address != staker
                or existing.agent_wallet != agent_wallet
                or existing.amount != amount
                or existing.lock_period != lock_period
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"Stake {stake_id} already exists with different terms",
                )
            return {
                "success": True,
                "idempotent": True,
                "stake_id": existing.stake_id,
                "amount": existing.amount,
                "status": existing.status,
                "locked_until": existing.locked_until.isoformat(),
            }
        lock_state = _agent_lock_in_flight(session, chain_id, str(stake_id), staker)
        if lock_state is not None:
            # #2628: a lock already queued or sealed for this stake_id means
            # a previous attempt died after queueing — rebuild the row
            # instead of queueing a second lock. stake_id is the
            # idempotency key, so the signed body stays authoritative.
            record = AgentStakeRecord(
                chain_id=chain_id,
                stake_id=str(stake_id),
                staker_address=staker,
                agent_wallet=agent_wallet,
                amount=amount,
                lock_period=lock_period,
                locked_until=datetime.now(UTC) + timedelta(days=lock_period),
                status="active",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return {
                "success": True,
                "idempotent": True,
                "stake_id": record.stake_id,
                "amount": record.amount,
                "status": record.status,
                "locked_until": record.locked_until.isoformat(),
                f"lock_{lock_state}": True,
            }
        account = _account(session, chain_id, staker)
        if account.balance < amount:
            raise HTTPException(status_code=400, detail=f"Insufficient balance: {account.balance} < {amount}")
        # Only the stake record is written here. The debit is carried by the
        # STAKE_LOCK transfer and applied at block time; mutating the account
        # table outside block processing desynchronises it from every block
        # header. See ``protocol_escrow``.
        locked_until = datetime.now(UTC) + timedelta(days=lock_period)
        # #2628: queue BEFORE the row commits — a refused queue leaves no
        # stake record, so the retry re-runs cleanly instead of answering
        # idempotent success for a lock that never queued.
        tx_hash = queue_protocol_transfer(
            sender=staker,
            recipient=stake_escrow_address(),
            amount=amount,
            chain_id=chain_id,
            tx_type="STAKE_LOCK",
            # v4: lock_days makes the unbonding window consensus-visible.
            payload={"agent_stake_id": str(stake_id), "lock_days": lock_period},
            # Operator-signed on the staker's behalf; carried into the block
            # record as the lock's provable authorization.
            auth={"signer": operator_address(), "message": payload, "signature": body.get("signature")},
        )
        record = AgentStakeRecord(
            chain_id=chain_id,
            stake_id=str(stake_id),
            staker_address=staker,
            agent_wallet=agent_wallet,
            amount=amount,
            lock_period=lock_period,
            locked_until=locked_until,
            status="active",
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        _logger.info("Agent stake lock queued: %s amount=%s staker=%s tx=%s", stake_id, amount, staker, tx_hash)
        return {
            "success": True,
            "stake_id": record.stake_id,
            "amount": record.amount,
            "status": record.status,
            "locked_until": record.locked_until.isoformat(),
            "transaction_hash": tx_hash,
            "message": "Stake lock submitted to mempool; the balance moves when the transaction is included in a block",
        }


@rate_limit(rate=20, per=60)
def add_to_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    try:
        _require_supported_chain(chain_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    _signed_stake_id_matches(payload, stake_id)
    additional = require_int(payload, "additional_amount")
    request_id = _topup_request_id(payload)
    user = payload.get("user_address")
    if not user:
        raise HTTPException(status_code=400, detail="user_address is required")
    user = _to_ait_address(str(user))
    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Agent staking (top-up)")
        record = _get_stake(session, chain_id, stake_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Stake {stake_id} not found")
        if record.staker_address != user:
            raise HTTPException(status_code=403, detail="user_address does not match the locked account")
        guarded = _canonical_guard(session, chain_id, stake_id, "add", owner=record.staker_address)
        if guarded is not None:
            return guarded
        early = _check_topup_request_id(session, chain_id, record, stake_id, request_id, additional)
        if early is not None:
            return early
        if record.status != "active":
            raise HTTPException(status_code=400, detail=f"Stake is not active: {record.status}")
        account = _account(session, chain_id, user)
        if account.balance < additional:
            raise HTTPException(status_code=400, detail=f"Insufficient balance: {account.balance} < {additional}")
        return _apply_agent_topup(
            session, chain_id, record, user, stake_id, additional, request_id, payload, body.get("signature")
        )


def _apply_agent_topup(
    session: Session,
    chain_id: str,
    record: AgentStakeRecord,
    user: str,
    stake_id: str,
    additional: int,
    request_id: str | None,
    payload: dict[str, Any],
    signature: Any,
) -> dict[str, Any]:
    """Queue the top-up lock, then grow the record — in that order (#2628).

    A lock already queued or sealed for this exact top-up reconciles the
    record instead of queueing a second lock; a ``request_id`` marks the
    memo so a re-sent body is a one-shot replay (#2627).
    """
    early = _reconcile_agent_topup(session, chain_id, record, additional, stake_id, request_id)
    if early is not None:
        if request_id is not None:
            session.add(_topup_request_memo(chain_id, stake_id, request_id, additional))
            session.commit()
        return early
    # Queue BEFORE the amount commits — a refused queue leaves the record
    # untouched so the retry re-runs cleanly.
    lock_payload = {
        "agent_stake_id": str(stake_id),
        "lock_days": record.lock_period,
        "additional_amount": additional,
    }
    if request_id is not None:
        # The idempotency key rides in the lock payload so the reconcile
        # above can tell this top-up from a same-amount one.
        lock_payload["request_id"] = request_id
    tx_hash = queue_protocol_transfer(
        sender=user,
        recipient=stake_escrow_address(),
        amount=additional,
        chain_id=chain_id,
        tx_type="STAKE_LOCK",
        # additional_amount marks the lock as a top-up so status reads can
        # tell it apart from the stake's original lock (#2456).
        payload=lock_payload,
        auth={"signer": operator_address(), "message": payload, "signature": signature},
    )
    record.amount += additional
    record.updated_at = datetime.now(UTC)
    session.add(record)
    if request_id is not None:
        session.add(_topup_request_memo(chain_id, stake_id, request_id, additional))
    session.commit()
    session.refresh(record)
    return {
        "success": True,
        "stake_id": str(stake_id),
        # #2456: `amount` used to echo the new TOTAL, so callers summing
        # top-ups over-counted by the whole stake. It now carries the
        # delta like every other amount field; the total is `new_total`.
        "amount": additional,
        "added_amount": additional,
        "new_total": record.amount,
        "transaction_hash": tx_hash,
        "message": "Stake top-up submitted to mempool; the balance moves when the transaction is included in a block",
    }


def _topup_request_id(payload: dict[str, Any]) -> str | None:
    """Optional client-chosen idempotency key for a top-up (#2627)."""
    raw = payload.get("request_id") or payload.get("nonce")
    if raw is None:
        return None
    rid = str(raw).strip()
    return rid or None


def _topup_request_memo(chain_id: str, stake_id: str, request_id: str, additional: int) -> AgentStakeMemo:
    return AgentStakeMemo(
        chain_id=chain_id,
        kind="topup_request",
        external_id=f"{stake_id}:{request_id}",
        payload={"stake_id": str(stake_id), "request_id": request_id, "additional_amount": additional},
    )


def _check_topup_request_id(
    session: Session,
    chain_id: str,
    record: AgentStakeRecord,
    stake_id: str,
    request_id: str | None,
    additional: int,
) -> dict[str, Any] | None:
    """#2627: a signed request_id is a one-shot idempotency key.

    Returns the idempotent-replay dict when the key was already consumed,
    raises 409 when it is reused with a different amount, and returns None
    to proceed.
    """
    if request_id is None:
        return None
    seen = session.exec(
        select(AgentStakeMemo).where(
            AgentStakeMemo.chain_id == chain_id,
            AgentStakeMemo.kind == "topup_request",
            AgentStakeMemo.external_id == f"{stake_id}:{request_id}",
        )
    ).first()
    if seen is None:
        return None
    stored = int((seen.payload or {}).get("additional_amount") or 0)
    if stored != additional:
        raise HTTPException(status_code=409, detail="request_id already used for a different top-up amount")
    return {
        "success": True,
        "idempotent": True,
        "stake_id": str(stake_id),
        "amount": additional,
        "added_amount": additional,
        "new_total": record.amount,
        "transaction_hash": None,
        "already_queued": True,
        "request_id": request_id,
        "message": "Stake top-up already applied for this request_id",
    }


def _reconcile_agent_topup(
    session: Session,
    chain_id: str,
    record: AgentStakeRecord,
    additional: int,
    stake_id: str,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    """#2628: settle a top-up whose STAKE_LOCK is already queued or sealed.

    ``record.amount`` must equal the sealed lock total once every queued
    lock has applied. For a matching lock (same ``agent_stake_id`` +
    ``additional_amount``) the record either already counts it
    (idempotent return), still owes the delta (a previous attempt died
    between queue and commit — apply it now, no second queue), or sits
    among other unresolved top-ups (409 — never guess).
    """
    # #3025: agent_stake_id is only unique per node — count and match only
    # locks this stake's staker actually sent; a foreign staker's top-up
    # lock under a colliding id must not reconcile this record.
    lock_txs = confirmed_lock_txs(session, chain_id, "STAKE_LOCK", "agent_stake_id", stake_id, sender=record.staker_address)
    accounted = sum(int(tx.value or 0) for tx in lock_txs)

    def _topup_lock_matches(tx: Any) -> bool:
        p = tx.payload or {}
        if str(p.get("additional_amount", "")) != str(additional):
            return False
        # #2627: a request_id-bearing lock is a different top-up than a
        # legacy unsigned-id body of the same amount — never consolidate.
        if request_id is None:
            return p.get("request_id") in (None, "")
        return str(p.get("request_id", "")) == request_id

    match_sealed = any(_topup_lock_matches(tx) for tx in lock_txs)
    # A pending lock's value is not in ``accounted`` yet; a sealed one's is.
    # ``request_id`` is always in the match: "" matches only entries that
    # lack the key, so a legacy body never consolidates onto a
    # request_id-bearing lock (and vice versa).
    match = {
        "agent_stake_id": str(stake_id),
        "additional_amount": additional,
        "request_id": request_id or "",
    }
    match_pending = protocol_transfer_pending(
        session,
        chain_id,
        "STAKE_LOCK",
        match,
        tx_match={"from": _to_ait_address(str(record.staker_address))},
    )
    if match_pending:
        applied_state = accounted + additional
    elif match_sealed:
        applied_state = accounted
    else:
        return None
    if record.amount == applied_state:
        already = True
    elif record.amount == applied_state - additional:
        record.amount += additional
        record.updated_at = datetime.now(UTC)
        session.add(record)
        session.commit()
        already = False
    else:
        raise HTTPException(
            status_code=409,
            detail="Unresolved agent-stake top-ups in flight; retry after the pending locks seal",
        )
    return {
        "success": True,
        "stake_id": str(stake_id),
        "amount": additional,
        "added_amount": additional,
        "new_total": record.amount,
        "transaction_hash": None,
        "already_queued": already,
        "message": "Stake top-up lock already queued; the balance moves when the transaction is included in a block",
    }


def _queue_unbond_marker_and_flip(
    session: Session,
    chain_id: str,
    record: AgentStakeRecord,
    stake_id: str,
    amount: int,
    payload: dict[str, Any],
    signature: Any,
) -> tuple[str | None, bool]:
    """#2628: queue the STAKE_UNBOND marker BEFORE the row flips.

    A refused queue raises before any commit, leaving the stake active so
    the retry re-runs cleanly. A marker already pending means a previous
    attempt died after queueing — flip the row without emitting a second
    marker. Returns ``(tx_hash, marker_pending)``.
    """
    # Same unscoped-UNBOND residual as _resync_stake_to_unbonding: the
    # marker's envelope is escrow→escrow, so a foreign pending marker under
    # a colliding agent_stake_id still counts (#3025).
    marker_pending = protocol_transfer_pending(session, chain_id, "STAKE_UNBOND", {"agent_stake_id": str(stake_id)})
    tx_hash = None
    if not marker_pending:
        tx_hash = queue_protocol_transfer(
            sender=stake_escrow_address(),
            recipient=stake_escrow_address(),
            amount=amount,
            chain_id=chain_id,
            tx_type="STAKE_UNBOND",
            payload={"agent_stake_id": str(stake_id)},
            auth={"signer": operator_address(), "message": payload, "signature": signature},
        )
    now = datetime.now(UTC)
    record.status = "unbonding"
    record.unbonding_at = now
    record.updated_at = now
    session.add(record)
    session.commit()
    return tx_hash, marker_pending


@rate_limit(rate=20, per=60)
def unbond_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    _signed_stake_id_matches(payload, stake_id)
    user = payload.get("user_address")
    if not user:
        raise HTTPException(status_code=400, detail="user_address is required")
    user = _to_ait_address(str(user))
    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Agent staking (unbond)")
        record = _get_stake(session, chain_id, stake_id)
        if not record:
            # Not 404-blind (#719): sealed history may know this stake even
            # though the local record lives on another host.
            return _no_local_record(session, chain_id, stake_id, "unbond", owner=user)
        if record.staker_address != user:
            raise HTTPException(status_code=403, detail="user_address does not match the locked account")
        guarded = _canonical_guard(session, chain_id, stake_id, "unbond", owner=record.staker_address)
        if guarded is not None:
            return guarded
        if record.status == "unbonding":
            return {
                "success": True,
                "idempotent": True,
                "stake_id": record.stake_id,
                "status": record.status,
                "funds_released": False,
                "next": "complete",
            }
        if record.status != "active":
            raise HTTPException(status_code=400, detail=f"Stake is not active: {record.status}")
        now = datetime.now(UTC)
        locked_until = record.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if now < locked_until:
            raise HTTPException(status_code=400, detail=f"Lock period not expired. Locked until: {locked_until.isoformat()}")
        amount = record.amount
        tx_hash, marker_pending = _queue_unbond_marker_and_flip(
            session, chain_id, record, stake_id, amount, payload, body.get("signature")
        )

    # STAKE_UNBOND marker (Option A, #719): the agent_stake row is
    # node-local, so the unbond transition was invisible off the serving
    # host. Emit a marker protocol transfer — an escrow->escrow
    # self-transfer of the stake amount (net-zero balance move, the
    # transfer semantics every version already replays) — so the
    # transition lands in sealed history on every host and the status read
    # becomes derivable from tx rows. Idempotent calls above return before
    # this and cannot double-emit.
    # "unbonding" is not "released" — funds stay locked until `complete`
    # emits the STAKE_RELEASE transfer. The response says so outright so
    # callers can't read the ok-shape as a finished unbond (Refs #719).
    return {
        "success": True,
        "stake_id": record.stake_id,
        "status": "unbonding",
        "funds_released": False,
        "next": "complete",
        "transaction_hash": tx_hash,
        "already_queued": marker_pending,
        "message": "Unbond marker submitted to mempool; the transition is consensus-visible once it is included in a block",
    }


def _complete_stake_prechecks(
    session: Any, chain_id: str, record: Any, user: str, stake_id: str
) -> tuple[dict[str, Any] | None, list[Any]]:
    """Validate a STAKE_RELEASE completion request.

    Returns ``(early_result, lock_txs)`` — ``early_result`` is the
    idempotent-replay dict when the stake already completed (caller returns
    it), or None when the release may proceed; ``lock_txs`` are the confirmed
    STAKE_LOCK txs the release spends. Raises HTTPException on refusal.
    """
    if record.staker_address != user:
        raise HTTPException(status_code=403, detail="user_address does not match the locked account")
    guarded = _canonical_guard(session, chain_id, stake_id, "complete", owner=record.staker_address)
    if guarded is not None:
        return guarded, []
    if record.status == "completed":
        return {"success": True, "idempotent": True, "stake_id": record.stake_id, "status": record.status}, []
    if record.status != "unbonding":
        raise HTTPException(status_code=400, detail=f"Stake is not unbonding: {record.status}")
    now = datetime.now(UTC)
    locked_until = record.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    if now < locked_until:
        raise HTTPException(status_code=400, detail="Lock period not expired")
    # The escrow is shared across all stakers, so the full principal must
    # be provably in it before any of it is released back. #3025:
    # agent_stake_id collides across nodes — claim only locks this staker
    # sent, or a foreign lock lands in lock_tx_hashes and consensus rejects
    # the release (every claimed lock's sender must be the payee).
    lock_txs = confirmed_lock_txs(
        session, chain_id, "STAKE_LOCK", "agent_stake_id", record.stake_id, sender=record.staker_address
    )
    funded = sum(int(tx.value or 0) for tx in lock_txs)
    if funded < record.amount:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Stake {record.stake_id} is not fully confirmed on-chain "
                f"({funded} of {record.amount} locked); retry once the lock transactions are in a block"
            ),
        )
    return None, lock_txs


def _check_lock_maturity(session: Any, chain_id: str, lock_txs: list[Any]) -> None:
    """Mirror the v4 consensus maturity window (height + lock_days*1440)
    so a release that block apply would reject fails here instead of
    after the record was already marked completed."""
    current_height = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).first() or 0
    if current_height < settings.state_transition_v4_height:
        return
    next_height = current_height + 1
    for lock in lock_txs:
        lock_days = (lock.payload or {}).get("lock_days")
        if lock_days in (None, 0):
            continue  # legacy / agent / auto-stake locks carry no window
        try:
            unlock_height = int(lock.block_height or 0) + int(str(lock_days)) * _STAKE_LOCK_BLOCKS_PER_DAY
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Lock {lock.tx_hash} has invalid lock_days") from None
        if next_height < unlock_height:
            raise HTTPException(
                status_code=400,
                detail=f"Lock {lock.tx_hash} matures at height {unlock_height}; current {next_height}",
            )


@rate_limit(rate=20, per=60)
def complete_agent_stake(request: Request, stake_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    try:
        _require_supported_chain(chain_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    _signed_stake_id_matches(payload, stake_id)
    user = payload.get("user_address")
    if not user:
        raise HTTPException(status_code=400, detail="user_address is required")
    user = _to_ait_address(str(user))
    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Agent staking (complete)")
        record = _get_stake(session, chain_id, stake_id)
        if not record:
            return _no_local_record(session, chain_id, stake_id, "complete", owner=user)
        early, lock_txs = _complete_stake_prechecks(session, chain_id, record, user, stake_id)
        if early is not None:
            return early
        _check_lock_maturity(session, chain_id, lock_txs)
        amount = record.amount
        if payload.get("resolve_only"):
            # Two-phase commit (#2472): re-sign with these resolved values
            # so payload.auth binds payee and amount for gossip admission.
            return {
                "success": True,
                "stake_id": str(stake_id),
                "resolved": {"to": user, "amount": amount},
            }
        require_signed_transfer_values(payload, to=user, amount=amount)
        if protocol_transfer_pending(
            session,
            chain_id,
            "STAKE_RELEASE",
            {"agent_stake_id": str(stake_id)},
            tx_match={"to": user},
        ):
            # #2628: a previous attempt queued the release but died before
            # the row flipped — the payout is already on its way, so answer
            # success without queueing a duplicate. The row stays
            # "unbonding" so a dropped mempool entry still retries cleanly.
            return {
                "success": True,
                "stake_id": str(stake_id),
                "status": "unbonding",
                "amount": amount,
                "release_pending": True,
                "message": "Stake release already queued; the balance moves when the transaction is included in a block",
            }
        # #2628: queue BEFORE the row flips — a refused queue leaves the
        # stake unbonding so the retry re-runs the release instead of
        # answering idempotent success for a payout that never queued.
        tx_hash = queue_protocol_transfer(
            sender=stake_escrow_address(),
            recipient=user,
            amount=amount,
            chain_id=chain_id,
            tx_type="STAKE_RELEASE",
            payload={
                "agent_stake_id": str(stake_id),
                # v4: the release spends exactly these replicated lock records.
                "lock_tx_hashes": [tx.tx_hash for tx in lock_txs],
            },
            auth={"signer": operator_address(), "message": payload, "signature": body.get("signature")},
        )
        record.status = "completed"
        record.updated_at = datetime.now(UTC)
        session.add(record)
        session.commit()
        return {
            "success": True,
            "stake_id": str(stake_id),
            "status": "completed",
            "amount": amount,
            "transaction_hash": tx_hash,
            "message": "Stake release submitted to mempool; the balance moves when the transaction is included in a block",
        }


def _write_memo(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    external_id = str(payload.get("stake_id") or payload.get("agent_wallet") or "")
    # #2631: dedupe on the signed body itself — a replayed operator-signed
    # memo is the same request, so it must not write a second row. The hash
    # covers the full canonical payload, so a genuinely different report
    # (different metrics, epoch, amount) still lands as a new memo.
    digest = payload_hash(payload)
    with session_scope() as session:
        existing = session.exec(
            select(AgentStakeMemo).where(
                AgentStakeMemo.chain_id == chain_id,
                AgentStakeMemo.kind == kind,
                AgentStakeMemo.external_id == external_id,
            )
        ).all()
        for memo in existing:
            if payload_hash(memo.payload) == digest:
                return {"success": True, "idempotent": True, "kind": kind, "external_id": external_id}
        memo = AgentStakeMemo(chain_id=chain_id, kind=kind, external_id=external_id, payload=payload)
        session.add(memo)
        session.commit()
    return {"success": True, "kind": kind, "external_id": external_id}


@rate_limit(rate=20, per=60)
def record_performance(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    return _write_memo("performance", body)


@rate_limit(rate=20, per=60)
def record_distribute(request: Request, agent_wallet: str, body: dict[str, Any]) -> dict[str, Any]:
    body = {**body, "agent_wallet": body.get("agent_wallet") or agent_wallet}
    return _write_memo("distribute", body)


@rate_limit(rate=20, per=60)
def record_claim(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    return _write_memo("claim", body)
