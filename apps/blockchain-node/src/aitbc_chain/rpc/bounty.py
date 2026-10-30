"""Bounty lock / memo RPC (V23-42)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from sqlmodel import Session, select

from aitbc.rate_limiting import rate_limit

from ..base_models import BountyContract, BountySubmissionRecord, _to_ait_address
from ..database import session_scope
from ..logger import get_logger
from ..models import Account
from ..protocol_escrow import (
    bounty_escrow_address,
    confirmed_lock_total,
    protocol_transfers_active,
    queue_protocol_transfer,
)
from .agent_economics_auth import operator_address, require_int, require_operator_signature
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


def _require_funded(session: Session, chain_id: str, bounty: BountyContract) -> None:
    """Refuse to pay out of the shared bounty escrow before the lock has landed.

    The BountyContract row is written as soon as the lock is queued -- it is not
    part of the state root, so it cannot desynchronise it -- but that means a
    bounty can look active while its funds are still in the mempool, or while
    the lock has been dropped because the creator spent the balance first.
    Paying then would come out of other creators' locked rewards.
    """
    funded = confirmed_lock_total(session, chain_id, "BOUNTY_LOCK", "bounty_id", bounty.bounty_id)
    if funded < bounty.reward_amount:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Bounty {bounty.bounty_id} is not fully confirmed on-chain "
                f"({funded} of {bounty.reward_amount} locked); retry once the lock transaction is in a block"
            ),
        )


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
    with session_scope() as session:
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Bounty (create)")
        existing = _get_bounty(session, chain_id, str(bounty_id))
        if existing:
            return {
                "success": True,
                "idempotent": True,
                "bounty_id": existing.bounty_id,
                "remaining_amount": existing.remaining_amount,
                "status": existing.status,
            }
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
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        result = {
            "success": True,
            "bounty_id": record.bounty_id,
            "remaining_amount": record.remaining_amount,
            "status": record.status,
        }

    tx_hash = queue_protocol_transfer(
        sender=creator,
        recipient=bounty_escrow_address(),
        amount=amount,
        chain_id=chain_id,
        tx_type="BOUNTY_LOCK",
        payload={"bounty_id": str(bounty_id)},
        auth={"signer": operator_address(), "message": payload, "signature": body.get("signature")},
    )
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
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Bounty (verify/payout)")
        bounty = _get_bounty(session, chain_id, bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail=f"Bounty {bounty_id} not found")
        if bounty.status in ("completed", "expired"):
            return {"success": True, "idempotent": True, "status": bounty.status}
        submission = session.exec(
            select(BountySubmissionRecord).where(
                BountySubmissionRecord.chain_id == chain_id, BountySubmissionRecord.submission_id == str(submission_id)
            )
        ).first()
        if not submission:
            raise HTTPException(status_code=404, detail=f"Submission {submission_id} not found")
        now = datetime.now(UTC)
        winner = None
        if verified:
            _require_funded(session, chain_id, bounty)
            winner = submission.submitter_address
            payout = bounty.remaining_amount
            bounty.remaining_amount = 0
            bounty.status = "completed"
            bounty.winner_address = winner
            submission.status = "verified"
        else:
            submission.status = "rejected"
            payout = 0
        submission.updated_at = now
        bounty.updated_at = now
        session.add(submission)
        session.add(bounty)
        session.commit()
        status = bounty.status

    result = {"success": True, "bounty_id": bounty_id, "status": status, "payout": payout}
    if winner and payout:
        result["transaction_hash"] = queue_protocol_transfer(
            sender=bounty_escrow_address(),
            recipient=winner,
            amount=payout,
            chain_id=chain_id,
            tx_type="BOUNTY_PAYOUT",
            payload={"bounty_id": str(bounty_id), "submission_id": str(submission_id)},
            auth={"signer": operator_address(), "message": payload, "signature": body.get("signature")},
        )
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
        if not protocol_transfers_active(session, chain_id):
            raise_for_unarmed("Bounty (expire/refund)")
        bounty = _get_bounty(session, chain_id, bounty_id)
        if not bounty:
            raise HTTPException(status_code=404, detail=f"Bounty {bounty_id} not found")
        if bounty.creator_address != user:
            raise HTTPException(status_code=403, detail="user_address does not match the locked account")
        if bounty.status == "expired":
            return {"success": True, "idempotent": True, "bounty_id": bounty.bounty_id, "refunded": 0}
        if bounty.status == "completed":
            raise HTTPException(status_code=400, detail="Bounty already completed")
        refund = bounty.remaining_amount
        if refund:
            _require_funded(session, chain_id, bounty)
        bounty.remaining_amount = 0
        bounty.status = "expired"
        bounty.updated_at = datetime.now(UTC)
        session.add(bounty)
        session.commit()
        status = bounty.status

    result = {"success": True, "bounty_id": bounty_id, "status": status, "refunded": refund}
    if refund:
        result["transaction_hash"] = queue_protocol_transfer(
            sender=bounty_escrow_address(),
            recipient=user,
            amount=refund,
            chain_id=chain_id,
            tx_type="BOUNTY_REFUND",
            payload={"bounty_id": str(bounty_id)},
            auth={"signer": operator_address(), "message": payload, "signature": body.get("signature")},
        )
        result["message"] = "Bounty refund submitted to mempool; the balance moves when the transaction is included in a block"
    return result
