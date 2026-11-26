"""Bounty lock / memo RPC (V23-42)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlmodel import Session, func, select

from aitbc.rate_limiting import rate_limit

from ..base_models import BountyContract, BountySubmissionRecord, _to_ait_address
from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Block
from ..protocol_escrow import (
    bounty_escrow_address,
    confirmed_lock_total,
    confirmed_lock_txs,
    protocol_transfers_active,
    queue_protocol_transfer,
)
from .agent_economics_auth import (
    operator_address,
    require_int,
    require_operator_signature,
    require_signed_transfer_values,
)
from .retired import raise_for_unarmed
from .utils import _require_supported_chain, get_chain_id, validate_chain_id

_logger = get_logger(__name__)


def _account(session: Session, chain_id: str, address: str) -> Account:
    account = session.get(Account, (chain_id, address))
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {address} not found")
    return account


def _get_bounty(session: Session, chain_id: str, bounty_id: str) -> BountyContract | None:
    return session.exec(
        select(BountyContract).where(BountyContract.chain_id == chain_id, BountyContract.bounty_id == bounty_id)
    ).first()


def _signed_bounty_id_matches(payload: dict[str, Any], bounty_id: str, *, required: bool = False) -> None:
    """If the signed body names a bounty_id it must be the path's.

    The auth embedded in the emitted tx is the signed body; a mismatch
    either fails the v17 binding at seal (payload.bounty_id != signed)
    after the record was already mutated, or silently authorizes a bounty
    other than the one the operator signed. Refuse up front.

    ``required=True`` — set on the payout path — also refuses a signed body
    with no bounty_id at all. A verified submission drains the bounty
    escrow, and the apply-time binding for BOUNTY_PAYOUT keys on
    ``submission_id`` only (bounty_id is compared just when the message
    carries it), so a signature naming no bounty could be re-pathed onto a
    different ``/bounty/{id}/verify`` and pay out of the wrong lock.

    Absence stays tolerated on every other path: submit/dispute move no
    escrow funds, the refund can only pay the signed creator, and
    signatures issued before the coordinator signed bounty_id keep
    working."""
    signed = payload.get("bounty_id")
    if signed is None:
        if required:
            raise HTTPException(status_code=400, detail="signed bounty_id is required for payout")
        return
    if str(signed) != str(bounty_id):
        raise HTTPException(status_code=400, detail="signed bounty_id does not match the path bounty_id")


def _optional_deadline_height(payload: dict[str, Any]) -> int | None:
    """Optional ``deadline_height`` from a signed deploy body.

    Absent (or null) keeps the legacy semantics: the bounty may be expired
    at any height. When set it is the earliest block height at which
    ``expire_bounty`` may run — see ``expire_bounty``.
    """
    raw = payload.get("deadline_height")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="deadline_height must be an integer") from exc
    if value < 0:
        raise HTTPException(status_code=400, detail="deadline_height must be >= 0")
    return value


def _bounty_flow_tx_pending(
    session: Any,
    chain_id: str,
    tx_type: str,
    bounty_id: str,
    tx_match: dict[str, Any] | None = None,
) -> bool:
    """True when a mempool entry already carries this bounty flow transfer.

    Mirrors ``protocol_auth_identity_pending``: the pending copy is what a
    retry must see before re-queueing, so a queued-but-unsealed payout or
    refund is not emitted twice. ``tx_match`` narrows on top-level envelope
    fields (``from``/``to``) for payload keys that are not globally unique
    (#3025) — an envelope field the entry does not carry cannot disprove
    ownership, so it still counts as pending (fail-safe toward "exists").
    """
    import json as _json

    try:
        from sqlmodel import select

        from ..mempool_common import MempoolEntry

        rows = session.exec(select(MempoolEntry.content).where(MempoolEntry.chain_id == chain_id)).all()
    except Exception:  # noqa: BLE001 - mempool table absent (tests/minimal schemas): no pending copies exist
        return False
    for content in rows:
        try:
            tx = _json.loads(content) if isinstance(content, str) else content
        except (TypeError, ValueError):
            continue
        if not isinstance(tx, dict) or tx.get("type") != tx_type:
            continue
        if tx_match and any(tx.get(k) is not None and str(tx.get(k)) != str(v) for k, v in tx_match.items()):
            continue
        if str((tx.get("payload") or {}).get("bounty_id", "")) == str(bounty_id):
            return True
    return False


def _bounty_flow_tx_exists(
    session: Any,
    chain_id: str,
    tx_type: str,
    bounty_id: str,
    *,
    sender: str | None = None,
    recipient: str | None = None,
) -> bool:
    """True when a BOUNTY_* transfer for this bounty is sealed or pending.

    ``confirmed_lock_txs`` matches any tx type by payload key, so it covers
    BOUNTY_PAYOUT/BOUNTY_REFUND/BOUNTY_LOCK alike; the pending half scans
    the mempool table the same way ``protocol_auth_identity_pending`` does.

    ``bounty_id`` is caller-chosen and only unique per node (#3025), so
    ``sender``/``recipient`` scope the claim to the envelope party that
    identifies *this* bounty's flow: locks are sent by the creator, refunds
    paid to the creator, payouts to the recorded winner.
    """
    if confirmed_lock_txs(session, chain_id, tx_type, "bounty_id", bounty_id, sender=sender, recipient=recipient):
        return True
    tx_match: dict[str, Any] = {}
    if sender is not None:
        tx_match["from"] = _to_ait_address(str(sender))
    if recipient is not None:
        tx_match["to"] = _to_ait_address(str(recipient))
    return _bounty_flow_tx_pending(session, chain_id, tx_type, bounty_id, tx_match or None)


def _heal_missing_outflow(
    session: Any,
    chain_id: str,
    bounty: BountyContract,
    submission_id: Any,
    payload: dict[str, Any],
    signature: Any,
) -> tuple[str, int] | None:
    """Queue the payout/refund a completed/expired bounty is missing (#2637).

    The state row can reach ``completed``/``expired`` while its transfer
    never queued (refused pool, restart between commit and queue). The
    idempotent branches call this so a retry repairs the money movement
    instead of answering success over a stranded lock. Returns
    ``(tx_hash, amount)`` when a transfer was queued, else ``None``.
    """
    if bounty.status == "completed":
        tx_type, recipient = "BOUNTY_PAYOUT", bounty.winner_address
    elif bounty.status == "expired":
        tx_type, recipient = "BOUNTY_REFUND", bounty.creator_address
    else:
        return None
    if not recipient or _bounty_flow_tx_exists(session, chain_id, tx_type, bounty.bounty_id, recipient=recipient):
        return None
    # No payout/refund exists at all, so the whole confirmed lock *this
    # creator* funded is owed — a foreign creator's colliding bounty_id
    # must not inflate the heal amount (#3025).
    amount = confirmed_lock_total(
        session, chain_id, "BOUNTY_LOCK", "bounty_id", bounty.bounty_id, sender=bounty.creator_address
    )
    if amount <= 0:
        _logger.warning(
            "Bounty %s is %s with no %s queued and no confirmed lock — cannot heal",
            bounty.bounty_id,
            bounty.status,
            tx_type,
        )
        return None
    out_payload: dict[str, Any] = {"bounty_id": str(bounty.bounty_id)}
    if tx_type == "BOUNTY_PAYOUT":
        # The apply-time binding keys on submission_id — carry the id the
        # operator signed so payload.auth stays admissible.
        out_payload["submission_id"] = str(submission_id)
    tx_hash = queue_protocol_transfer(
        sender=bounty_escrow_address(),
        recipient=str(recipient),
        amount=amount,
        chain_id=chain_id,
        tx_type=tx_type,
        payload=out_payload,
        auth={"signer": operator_address(), "message": payload, "signature": signature},
    )
    _logger.warning("Healed missing %s for bounty %s: tx=%s amount=%s", tx_type, bounty.bounty_id, tx_hash, amount)
    return tx_hash, amount


def _heal_missing_lock(
    session: Any, chain_id: str, bounty: BountyContract, payload: dict[str, Any], signature: Any
) -> str | None:
    """Re-queue the BOUNTY_LOCK an existing bounty row lost (#2637).

    A deploy whose queue was refused used to leave an ``active`` row with
    no lock behind it — submissions accepted, verify/expire unfundable.
    The idempotent deploy branch calls this so the retry restores the
    escrow leg. Returns the tx hash when one was queued, else ``None``.
    """
    if _bounty_flow_tx_exists(session, chain_id, "BOUNTY_LOCK", bounty.bounty_id, sender=bounty.creator_address):
        return None
    lock_payload: dict[str, Any] = {"bounty_id": str(bounty.bounty_id)}
    if bounty.deadline_height is not None:
        lock_payload["deadline_height"] = bounty.deadline_height
    return queue_protocol_transfer(
        sender=bounty.creator_address,
        recipient=bounty_escrow_address(),
        amount=bounty.reward_amount,
        chain_id=chain_id,
        tx_type="BOUNTY_LOCK",
        payload=lock_payload,
        auth={"signer": operator_address(), "message": payload, "signature": signature},
    )


def _queue_payout_and_complete(
    chain_id: str,
    bounty: BountyContract,
    submission: BountySubmissionRecord,
    bounty_id: str,
    submission_id: Any,
    payload: dict[str, Any],
    signature: Any,
    winner: str,
    payout: int,
) -> str:
    """Queue the BOUNTY_PAYOUT, then flip bounty+submission to paid (#2637).

    The queue runs before the caller commits the state flip: a refused
    queue raises with the row untouched, so the retry redoes the verify
    instead of hitting the idempotent branch over a missing payout.
    Returns the queued transaction hash.
    """
    tx_hash = queue_protocol_transfer(
        sender=bounty_escrow_address(),
        recipient=winner,
        amount=payout,
        chain_id=chain_id,
        tx_type="BOUNTY_PAYOUT",
        payload={"bounty_id": str(bounty_id), "submission_id": str(submission_id)},
        auth={"signer": operator_address(), "message": payload, "signature": signature},
    )
    bounty.remaining_amount = 0
    bounty.status = "completed"
    bounty.winner_address = winner
    submission.status = "verified"
    return tx_hash


def _require_funded(session: Session, chain_id: str, bounty: BountyContract) -> None:
    """Refuse to pay out of the shared bounty escrow before the lock has landed.

    The BountyContract row is written as soon as the lock is queued -- it is not
    part of the state root, so it cannot desynchronise it -- but that means a
    bounty can look active while its funds are still in the mempool, or while
    the lock has been dropped because the creator spent the balance first.
    Paying then would come out of other creators' locked rewards.
    """
    funded = confirmed_lock_total(
        session, chain_id, "BOUNTY_LOCK", "bounty_id", bounty.bounty_id, sender=bounty.creator_address
    )
    if funded < bounty.reward_amount:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Bounty {bounty.bounty_id} is not fully confirmed on-chain "
                f"({funded} of {bounty.reward_amount} locked); retry once the lock transaction is in a block"
            ),
        )


def _deploy_existing_bounty(
    session: Any,
    chain_id: str,
    existing: BountyContract,
    creator: str,
    amount: int,
    deadline_height: int | None,
    payload: dict[str, Any],
    signature: Any,
) -> dict[str, Any]:
    """Idempotent branch for an existing bounty_id (#2637/#2641).

    Idempotent only when the stored record IS this request — a replay
    naming another creator, amount or deadline is a 409, not silent
    success. A matching retry heals a lost BOUNTY_LOCK instead of
    reporting success over an unfunded bounty.
    """
    if existing.creator_address != creator or existing.reward_amount != amount or existing.deadline_height != deadline_height:
        raise HTTPException(status_code=409, detail=f"Bounty {existing.bounty_id} already exists with different terms")
    healed = _heal_missing_lock(session, chain_id, existing, payload, signature)
    result: dict[str, Any] = {
        "success": True,
        "idempotent": True,
        "bounty_id": existing.bounty_id,
        "remaining_amount": existing.remaining_amount,
        "status": existing.status,
        "deadline_height": existing.deadline_height,
    }
    if healed:
        result["transaction_hash"] = healed
    return result


@rate_limit(rate=20, per=60)
def deploy_bounty(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    if not validate_chain_id(chain_id):
        raise HTTPException(status_code=400, detail=f"Unsupported chain_id: {chain_id}")
    bounty_id = payload.get("bounty_id")
    creator = payload.get("user_address") or payload.get("creator_address")
    if not bounty_id or not creator:
        raise HTTPException(status_code=400, detail="bounty_id and user_address are required")
    creator = _to_ait_address(str(creator))
    amount = require_int(payload, "reward_amount")
    deadline_height = _optional_deadline_height(payload)
    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Bounty (create)")
        existing = _get_bounty(session, chain_id, str(bounty_id))
        if existing is not None:
            return _deploy_existing_bounty(
                session, chain_id, existing, creator, amount, deadline_height, payload, body.get("signature")
            )
        account = _account(session, chain_id, creator)
        if account.balance < amount:
            raise HTTPException(status_code=400, detail=f"Insufficient balance: {account.balance} < {amount}")
        # Only the contract row is written here. The debit rides on the
        # BOUNTY_LOCK transfer and is applied at block time; see
        # ``protocol_escrow`` for why the account table must not be touched.
        record = BountyContract(
            chain_id=chain_id,
            bounty_id=str(bounty_id),
            creator_address=creator,
            reward_amount=amount,
            remaining_amount=amount,
            status="active",
            deadline_height=deadline_height,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        result = {
            "success": True,
            "bounty_id": record.bounty_id,
            "remaining_amount": record.remaining_amount,
            "status": record.status,
            "deadline_height": record.deadline_height,
        }

    lock_payload: dict[str, Any] = {"bounty_id": str(bounty_id)}
    if deadline_height is not None:
        # Carried on the sealed BOUNTY_LOCK so the on-chain record shows the
        # deadline the signed body committed to.
        lock_payload["deadline_height"] = deadline_height
    try:
        tx_hash = queue_protocol_transfer(
            sender=creator,
            recipient=bounty_escrow_address(),
            amount=amount,
            chain_id=chain_id,
            tx_type="BOUNTY_LOCK",
            payload=lock_payload,
            auth={"signer": operator_address(), "message": payload, "signature": body.get("signature")},
        )
    except Exception:  # noqa: BLE001 - any queue refusal must not strand the row
        # #2637: the BountyContract row is already committed — remove it so
        # the retry deploys cleanly instead of hitting the idempotent
        # branch over a bounty that has no lock behind it.
        with session_scope() as cleanup:
            orphan = _get_bounty(cleanup, chain_id, str(bounty_id))
            if orphan is not None:
                cleanup.delete(orphan)
                cleanup.commit()
        raise
    _logger.info("Bounty lock queued: %s amount=%s creator=%s tx=%s", bounty_id, amount, creator, tx_hash)
    result["transaction_hash"] = tx_hash
    result["message"] = "Bounty lock submitted to mempool; the balance moves when the transaction is included in a block"
    return result


@rate_limit(rate=20, per=60)
def submit_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    _signed_bounty_id_matches(payload, bounty_id)
    submission_id = payload.get("submission_id")
    submitter = payload.get("user_address")
    if not submission_id or not submitter:
        raise HTTPException(status_code=400, detail="submission_id and user_address are required")
    submitter = _to_ait_address(str(submitter))
    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Bounty (submit)")
        bounty = _get_bounty(session, chain_id, bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail=f"Bounty {bounty_id} not found")
        if bounty.status not in ("active", "submitted"):
            raise HTTPException(status_code=400, detail=f"Bounty is not open: {bounty.status}")
        existing = session.exec(
            select(BountySubmissionRecord).where(
                BountySubmissionRecord.chain_id == chain_id, BountySubmissionRecord.submission_id == str(submission_id)
            )
        ).first()
        if existing:
            # #2639: submission_id is unique per chain — idempotent only
            # when the stored row IS this request. The same id pointed at
            # another bounty (or another submitter) must not answer
            # success while recording nothing.
            if existing.bounty_id != bounty_id or existing.submitter_address != submitter:
                raise HTTPException(
                    status_code=409,
                    detail=f"Submission {submission_id} already exists for a different bounty or submitter",
                )
            return {"success": True, "idempotent": True, "submission_id": existing.submission_id}
        record = BountySubmissionRecord(
            chain_id=chain_id,
            bounty_id=bounty_id,
            submission_id=str(submission_id),
            submitter_address=submitter,
            status="pending",
            payload=payload,
        )
        if bounty.status == "active":
            bounty.status = "submitted"
            bounty.updated_at = datetime.now(UTC)
            session.add(bounty)
        session.add(record)
        session.commit()
        return {"success": True, "submission_id": record.submission_id, "status": record.status}


def _verify_bounty_locked(
    session: Any,
    chain_id: str,
    bounty_id: str,
    submission_id: Any,
    verified: bool,
    payload: dict[str, Any],
    signature: Any,
) -> tuple[dict[str, Any] | None, int, str | None, str | None]:
    """Validate, resolve, reject or pay inside the session.

    Returns ``(early_response, payout, status, payout_tx_hash)``: an early
    response ends the request (idempotent replay or the ``resolve_only``
    probe), a ``None`` early response means the row was mutated and
    committed — the payout transfer, when verified, is already queued.
    """
    if not protocol_transfers_active(session, chain_id):
        raise_for_unarmed("Bounty (verify/payout)")
    bounty = _get_bounty(session, chain_id, bounty_id)
    if not bounty:
        raise HTTPException(status_code=404, detail=f"Bounty {bounty_id} not found")
    if bounty.status in ("completed", "expired"):
        # #2637: idempotent only when the money actually moved — a
        # completed/expired row whose transfer never queued gets it
        # queued now instead of answering success over a stranded lock.
        healed = _heal_missing_outflow(session, chain_id, bounty, submission_id, payload, signature)
        early = {"success": True, "idempotent": True, "status": bounty.status}
        if healed:
            early["transaction_hash"], early["healed_amount"] = healed
        return early, 0, None, None
    if bounty.status == "disputed":
        # #2640: a dispute freezes the bounty — verify must not pay out
        # (or reject) while the outcome is contested.
        raise HTTPException(
            status_code=409,
            detail=f"Bounty {bounty_id} is disputed — payout is frozen until the dispute is resolved",
        )
    submission = session.exec(
        select(BountySubmissionRecord).where(
            BountySubmissionRecord.chain_id == chain_id,
            BountySubmissionRecord.submission_id == str(submission_id),
            # #2638: submission_id is unique per chain, not per bounty —
            # without this predicate a submission made to bounty A could
            # be "verified" against bounty B and paid out of B's lock.
            BountySubmissionRecord.bounty_id == str(bounty_id),
        )
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
    now = datetime.now(UTC)
    payout = 0
    payout_tx_hash = None
    if verified:
        _require_funded(session, chain_id, bounty)
        winner = submission.submitter_address
        payout = bounty.remaining_amount
        if payload.get("resolve_only"):
            # Two-phase commit (#2472): the caller re-signs a body that
            # carries these resolved values so payload.auth binds the
            # payee and amount for gossip admission.
            return {"success": True, "bounty_id": bounty_id, "resolved": {"to": winner, "amount": payout}}, payout, None, None
        require_signed_transfer_values(payload, to=winner, amount=payout)
        payout_tx_hash = _queue_payout_and_complete(
            chain_id,
            bounty,
            submission,
            bounty_id,
            submission_id,
            payload,
            signature,
            winner,
            payout,
        )
    else:
        submission.status = "rejected"
    submission.updated_at = now
    bounty.updated_at = now
    session.add(submission)
    session.add(bounty)
    session.commit()
    return None, payout, bounty.status, payout_tx_hash


@rate_limit(rate=20, per=60)
def verify_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    try:
        _require_supported_chain(chain_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    submission_id = payload.get("submission_id")
    verified = bool(payload.get("verified"))
    _signed_bounty_id_matches(payload, bounty_id, required=verified)
    if not submission_id:
        raise HTTPException(status_code=400, detail="submission_id is required")
    with session_scope() as session:
        early, payout, status, payout_tx_hash = _verify_bounty_locked(
            session, chain_id, bounty_id, submission_id, verified, payload, body.get("signature")
        )
        if early is not None:
            return early

    result = {"success": True, "bounty_id": bounty_id, "status": status, "payout": payout}
    if payout_tx_hash:
        result["transaction_hash"] = payout_tx_hash
        result["message"] = "Bounty payout submitted to mempool; the balance moves when the transaction is included in a block"
    return result


@rate_limit(rate=20, per=60)
def dispute_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    _signed_bounty_id_matches(payload, bounty_id)
    submission_id = payload.get("submission_id")
    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Bounty (dispute)")
        bounty = _get_bounty(session, chain_id, bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail=f"Bounty {bounty_id} not found")
        if bounty.status == "completed":
            raise HTTPException(status_code=400, detail="Cannot dispute a paid bounty")
        if bounty.status == "expired":
            # The refund already left the escrow — a dispute label now
            # would freeze a bounty whose money already moved.
            raise HTTPException(status_code=400, detail="Cannot dispute an expired bounty")
        if bounty.status == "disputed":
            return {"success": True, "idempotent": True, "bounty_id": bounty_id, "status": bounty.status}
        bounty.status = "disputed"
        bounty.updated_at = datetime.now(UTC)
        if submission_id:
            submission = session.exec(
                select(BountySubmissionRecord).where(
                    BountySubmissionRecord.chain_id == chain_id,
                    BountySubmissionRecord.submission_id == str(submission_id),
                )
            ).first()
            if submission:
                submission.status = "disputed"
                submission.updated_at = bounty.updated_at
                session.add(submission)
        session.add(bounty)
        session.commit()
        return {"success": True, "bounty_id": bounty_id, "status": bounty.status}


def _require_deadline_reached(session: Session, chain_id: str, bounty: BountyContract) -> None:
    """Refuse expiry while the chain head is below the bounty's deadline.

    A bounty with a ``deadline_height`` may only be expired once the head
    reaches it. Bounties deployed without one (``deadline_height`` NULL)
    keep the legacy expire-anytime semantics.
    """
    if bounty.deadline_height is None:
        return
    head = session.exec(select(func.max(Block.height)).where(Block.chain_id == chain_id)).first() or 0
    if head < bounty.deadline_height:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Bounty {bounty.bounty_id} deadline not reached: expires at height {bounty.deadline_height}, current {head}"
            ),
        )


def _expire_bounty_locked(
    session: Any, chain_id: str, bounty_id: str, user: str, payload: dict[str, Any], signature: Any
) -> tuple[dict[str, Any] | None, int, str | None, str | None]:
    """Validate, resolve or expire the bounty row inside the session.

    Returns ``(early_response, refund, status, refund_tx_hash)``: an early
    response ends the request (idempotent replay or the ``resolve_only``
    probe), a ``None`` early response means the row was mutated to expired
    and the refund transfer is already queued.
    """
    if not protocol_transfers_active(session, chain_id):
        raise_for_unarmed("Bounty (expire/refund)")
    bounty = _get_bounty(session, chain_id, bounty_id)
    if not bounty:
        raise HTTPException(status_code=404, detail=f"Bounty {bounty_id} not found")
    if bounty.creator_address != user:
        raise HTTPException(status_code=403, detail="user_address does not match the locked account")
    if bounty.status == "expired":
        # #2637: idempotent only when the refund actually queued — heal a
        # missing BOUNTY_REFUND instead of reporting success over a
        # stranded lock.
        healed = _heal_missing_outflow(session, chain_id, bounty, None, payload, signature)
        early = {"success": True, "idempotent": True, "bounty_id": bounty.bounty_id, "refunded": 0}
        if healed:
            early["transaction_hash"], early["refunded"] = healed
        return early, 0, None, None
    if bounty.status == "completed":
        raise HTTPException(status_code=400, detail="Bounty already completed")
    if bounty.status == "disputed":
        # #2640: a dispute freezes the bounty — expire must not refund
        # while the outcome is contested.
        raise HTTPException(
            status_code=409,
            detail=f"Bounty {bounty_id} is disputed — refund is frozen until the dispute is resolved",
        )
    _require_deadline_reached(session, chain_id, bounty)
    refund = bounty.remaining_amount
    if payload.get("resolve_only"):
        return (
            {
                "success": True,
                "bounty_id": bounty_id,
                "resolved": {"to": user, "amount": refund},
            },
            refund,
            None,
            None,
        )
    refund_tx_hash = None
    if refund:
        _require_funded(session, chain_id, bounty)
        require_signed_transfer_values(payload, to=user, amount=refund)
        # #2637: queue BEFORE committing the state flip — a refused queue
        # must leave the row untouched so the retry redoes the expire.
        refund_tx_hash = queue_protocol_transfer(
            sender=bounty_escrow_address(),
            recipient=user,
            amount=refund,
            chain_id=chain_id,
            tx_type="BOUNTY_REFUND",
            payload={"bounty_id": str(bounty_id)},
            auth={"signer": operator_address(), "message": payload, "signature": signature},
        )
    bounty.remaining_amount = 0
    bounty.status = "expired"
    bounty.updated_at = datetime.now(UTC)
    session.add(bounty)
    session.commit()
    return None, refund, bounty.status, refund_tx_hash


@rate_limit(rate=20, per=60)
def expire_bounty(request: Request, bounty_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = require_operator_signature(body)
    chain_id = get_chain_id(payload.get("chain_id"))
    try:
        _require_supported_chain(chain_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    _signed_bounty_id_matches(payload, bounty_id)
    user = payload.get("user_address")
    if not user:
        raise HTTPException(status_code=400, detail="user_address is required")
    user = _to_ait_address(str(user))
    with session_scope() as session:
        early, refund, status, refund_tx_hash = _expire_bounty_locked(
            session, chain_id, bounty_id, user, payload, body.get("signature")
        )
        if early is not None:
            return early

    result = {"success": True, "bounty_id": bounty_id, "status": status, "refunded": refund}
    if refund_tx_hash:
        result["transaction_hash"] = refund_tx_hash
        result["message"] = "Bounty refund submitted to mempool; the balance moves when the transaction is included in a block"
    return result
