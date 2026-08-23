"""
Escrow RPC endpoints for the blockchain node.
Provides create/release/refund/get endpoints backed by EscrowManager and Escrow DB model.

From v0.24.0 escrows are chain-backed: the buyer must submit a signed
ESCROW_LOCK transaction before an escrow can be created, and release submits an
ESCROW_RELEASE transaction from the node wallet to the provider.  This removes
the historical "unbacked payout" path.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException

from aitbc.constants import BLOCKCHAIN_RPC_URL
from aitbc.crypto.crypto import sign_transaction_hash
from aitbc.crypto.signature_recovery import canonical_address
from aitbc.network import SharedHttpClient
from eth_utils import keccak

from ..contracts.escrow import get_escrow_manager
from ..database import session_scope
from ..logger import get_logger
from ..models import Escrow

_HUB_RPC_URL = os.getenv("HUB_RPC_URL", BLOCKCHAIN_RPC_URL)
_CHAIN_ID = os.getenv("CHAIN_ID", os.getenv("SUPPORTED_CHAINS", "ait-hub.aitbc.bubuit.net"))
_NODE_WALLET = os.getenv("NODE_WALLET_ADDRESS", os.getenv("GENESIS_WALLET_ADDRESS", ""))
_logger = get_logger(__name__)
router = APIRouter(tags=["escrow"])


def _to_canonical(address: str) -> str:
    """Return the ait1/canonical form of an address, falling back to input."""
    try:
        return canonical_address(address)
    except Exception:
        return str(address)


async def _resolve_chain_account(address: str) -> str | None:
    """Return address if it exists on-chain, else None."""
    try:
        r = await SharedHttpClient.get(f"{_HUB_RPC_URL}/accounts/{address}")
        if r.status_code == 200:
            return address
    except Exception:  # nosec B110 - intentional silent failure
        pass
    return None


async def _get_account_nonce(address: str) -> int:
    """Fetch current nonce for an account from the chain."""
    try:
        r = await SharedHttpClient.get(f"{_HUB_RPC_URL}/accounts/{address}")
        if r.status_code == 200:
            return int(r.json().get("nonce", 0))
    except Exception:
        pass
    return 0


_GENESIS_WALLET_PRIVATE_KEY = os.getenv("GENESIS_WALLET_PRIVATE_KEY", "")


def _compute_tx_signing_hash(tx: dict[str, Any]) -> str:
    """Return the keccak hash the RPC verifies for a transaction signature."""
    has_amount = "amount" in tx
    tx_for_sign = {k: v for k, v in tx.items() if k not in ("signature", "sig") and not (has_amount and k == "value")}
    canonical = json.dumps(tx_for_sign, sort_keys=True, separators=(",", ":")).encode()
    return "0x" + keccak(canonical).hex()


async def _create_account_if_missing(address: str, chain_id: str) -> bool:
    """Ensure ``address`` has an on-chain account; create it if missing."""
    try:
        r = await SharedHttpClient.get(f"{_HUB_RPC_URL}/accounts/{address}")
        if r.status_code == 200:
            return True
        r = await SharedHttpClient.post(
            f"{_HUB_RPC_URL}/register-account",
            json={"address": canonical_address(address), "chain_id": chain_id},
            timeout=5.0,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        _logger.warning("ESCROW: account creation check failed for %s: %s", address, e)
    return False


def _ait_to_seconds(amount_ait: Decimal) -> int:
    """Convert AIT amount to compute-seconds (1 AIT = 3600)."""
    seconds = int(amount_ait * 3600)
    return seconds if seconds > 0 else int(amount_ait)


def _fee_for(amount: int) -> int:
    """Default network fee for an escrow transaction."""
    return max(36, amount // 100)


def _build_lock_tx(
    job_id: str,
    buyer: str,
    provider: str,
    amount_dec: Decimal,
    nonce: int,
    fee: int | None = None,
) -> tuple[dict[str, Any], int]:
    """Build the canonical ESCROW_LOCK transaction dict and return it with the seconds amount."""
    amount_seconds = _ait_to_seconds(amount_dec)
    if amount_seconds <= 0:
        raise ValueError("escrow amount must be positive")
    if not _NODE_WALLET:
        raise ValueError("NODE_WALLET_ADDRESS / GENESIS_WALLET_ADDRESS not configured")
    if fee is None:
        fee = _fee_for(amount_seconds)
    tx: dict[str, Any] = {
        "from": _to_canonical(buyer),
        "to": _to_canonical(_NODE_WALLET),
        "amount": amount_seconds,
        "fee": fee,
        "nonce": nonce,
        "type": "ESCROW_LOCK",
        "chain_id": _CHAIN_ID,
        "payload": {
            "action": "escrow_lock",
            "job_id": job_id,
            "provider": _to_canonical(provider),
        },
    }
    return tx, amount_seconds


async def _submit_lock_tx(signed_lock_tx: dict[str, Any]) -> str:
    """Submit a signed ESCROW_LOCK transaction and return its hash."""
    tx = dict(signed_lock_tx)
    # Map "sig" to the key the marketplace endpoint expects if only "sig" is present.
    if "signature" not in tx and "sig" in tx:
        tx["signature"] = tx.pop("sig")
    resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/marketplace", json=tx, timeout=10.0)
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=400, detail=f"ESCROW_LOCK transaction submission failed: {resp.status_code} {resp.text[:200]}"
        )
    result = resp.json()
    tx_hash = result.get("transaction_hash")
    if not tx_hash:
        raise HTTPException(status_code=400, detail="ESCROW_LOCK transaction accepted but no transaction_hash returned")
    _logger.info(
        "ESCROW_LOCK TX submitted: hash=%s from=%s to=%s amount=%s", tx_hash, tx.get("from"), tx.get("to"), tx.get("amount")
    )
    return str(tx_hash)


async def _submit_payment_tx(provider: str, amount: Decimal, job_id: str, contract_id: str) -> str | None:
    """Submit an ESCROW_RELEASE transaction to the blockchain so payment is on-chain."""
    amount_seconds = _ait_to_seconds(amount)
    if amount_seconds <= 0:
        return None
    try:
        if not _GENESIS_WALLET_PRIVATE_KEY:
            _logger.warning("ESCROW_RELEASE TX skipped: GENESIS_WALLET_PRIVATE_KEY not configured")
            return None

        if not _NODE_WALLET:
            _logger.warning("ESCROW_RELEASE TX skipped: NODE_WALLET_ADDRESS / GENESIS_WALLET_ADDRESS not configured")
            return None

        # The provider account must exist before a TRANSFER-style transaction can be applied.
        if not await _create_account_if_missing(provider, _CHAIN_ID):
            _logger.warning("ESCROW_RELEASE TX skipped: could not create provider account (provider=%s)", provider)
            return None

        # Release from the node wallet (where buyer funds were locked) to the provider.
        sender = _to_canonical(_NODE_WALLET)
        recipient = _to_canonical(provider)

        nonce = await _get_account_nonce(sender)
        tx = {
            "from": sender,
            "to": recipient,
            "amount": amount_seconds,
            "fee": _fee_for(amount_seconds),
            "nonce": nonce,
            "type": "ESCROW_RELEASE",
            "chain_id": _CHAIN_ID,
            "payload": {
                "action": "escrow_release",
                "job_id": job_id,
                "contract_id": contract_id,
                "provider_escrow_addr": recipient,
                "released_at": datetime.now(UTC).isoformat(),
            },
        }
        signing_hash = _compute_tx_signing_hash(tx)
        tx["signature"] = sign_transaction_hash(signing_hash, _GENESIS_WALLET_PRIVATE_KEY)

        resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/marketplace", json=tx, timeout=5.0)
        if resp.status_code in (200, 201):
            result = resp.json()
            actual_tx_hash = result.get("transaction_hash")
            _logger.info(
                "ESCROW_RELEASE TX submitted: hash=%s amount=%s from=%s to=%s",
                actual_tx_hash,
                amount_seconds,
                sender,
                recipient,
            )
            return str(actual_tx_hash)
        _logger.warning("ESCROW_RELEASE TX failed %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        _logger.warning("ESCROW_RELEASE TX submission failed (non-fatal): %s", e)
    return None


@router.post("/escrow/create", summary="Create escrow for a job")
async def create_escrow(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new escrow contract after the buyer has signed an ESCROW_LOCK transaction.

    The request must include either a fully signed `lock_tx` dict or the
    `lock_signature` plus the lock transaction fields (nonce/fee).  The lock
    transaction must transfer the escrow amount from the buyer to the node
    wallet and include the job_id and provider in the payload.
    """
    job_id = body.get("job_id")
    buyer = body.get("buyer")
    provider = body.get("provider")
    amount = body.get("amount")
    if not all([job_id, buyer, provider, amount is not None]):
        raise HTTPException(status_code=400, detail="job_id, buyer, provider, and amount are required")

    try:
        amount_dec = Decimal(str(amount))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid amount: {amount}") from None

    if not isinstance(job_id, str) or not isinstance(buyer, str) or not isinstance(provider, str):
        raise HTTPException(status_code=400, detail="Invalid types for job_id, buyer, or provider") from None

    if amount_dec <= 0:
        raise HTTPException(status_code=400, detail="escrow amount must be positive") from None

    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    success, message, contract_id = await mgr.create_contract(
        job_id=job_id, client_address=buyer, agent_address=provider, amount=amount_dec
    )
    if not success:
        raise HTTPException(status_code=400, detail=message) from None

    # Accept a pre-built signed lock tx or build one from the provided signature.
    signed_lock_tx = body.get("lock_tx")
    lock_signature = body.get("lock_signature")

    if signed_lock_tx:
        if not isinstance(signed_lock_tx, dict):
            raise HTTPException(status_code=400, detail="lock_tx must be an object") from None
        if signed_lock_tx.get("type") != "ESCROW_LOCK":
            raise HTTPException(status_code=400, detail="lock_tx type must be ESCROW_LOCK") from None
        tx_to_submit = signed_lock_tx
    elif lock_signature:
        nonce = body.get("lock_nonce")
        if nonce is None:
            nonce = await _get_account_nonce(_to_canonical(buyer))
        try:
            nonce = int(nonce)
        except Exception:
            raise HTTPException(status_code=400, detail="lock_nonce must be an integer") from None
        fee = body.get("lock_fee")
        if fee is not None:
            try:
                fee = int(fee)
            except Exception:
                raise HTTPException(status_code=400, detail="lock_fee must be an integer") from None
        try:
            tx_to_submit, amount_seconds = _build_lock_tx(job_id, buyer, provider, amount_dec, nonce, fee)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        tx_to_submit["signature"] = lock_signature
    else:
        raise HTTPException(status_code=400, detail="escrow lock is required: provide lock_tx or lock_signature") from None

    # Verify the lock tx moves the expected amount to the node wallet.
    try:
        expected_tx, expected_amount = _build_lock_tx(job_id, buyer, provider, amount_dec, tx_to_submit.get("nonce", 0))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    if tx_to_submit.get("from") != expected_tx["from"]:
        raise HTTPException(status_code=400, detail="lock_tx from must be the buyer") from None
    if _to_canonical(tx_to_submit.get("to", "")) != _to_canonical(expected_tx["to"]):
        raise HTTPException(status_code=400, detail="lock_tx to must be the node wallet") from None
    if int(tx_to_submit.get("amount", 0)) != expected_amount:
        raise HTTPException(status_code=400, detail=f"lock_tx amount must be {expected_amount}") from None
    payload = tx_to_submit.get("payload") or {}
    if payload.get("job_id") != job_id:
        raise HTTPException(status_code=400, detail="lock_tx payload job_id mismatch") from None
    if _to_canonical(payload.get("provider", "")) != _to_canonical(provider):
        raise HTTPException(status_code=400, detail="lock_tx payload provider mismatch") from None

    # Ensure the buyer has an on-chain account before the lock tx is admitted.
    if not await _create_account_if_missing(_to_canonical(buyer), _CHAIN_ID):
        raise HTTPException(status_code=400, detail=f"could not ensure buyer account exists: {buyer}") from None

    lock_tx_hash = await _submit_lock_tx(tx_to_submit)

    if contract_id is None:
        raise HTTPException(status_code=500, detail="escrow contract_id missing after create")

    # Fund the in-memory contract now that the lock has been submitted.
    await mgr.fund_contract(contract_id, lock_tx_hash)

    try:
        with session_scope() as session:
            existing = session.get(Escrow, job_id)
            if existing:
                existing.status = "locked"
                existing.lock_tx_hash = lock_tx_hash
                existing.buyer = _to_canonical(buyer)
                existing.provider = _to_canonical(provider)
                existing.amount = int(amount_dec)
            else:
                escrow_record = Escrow(
                    job_id=job_id,
                    buyer=_to_canonical(buyer),
                    provider=_to_canonical(provider),
                    amount=int(amount_dec),
                    status="locked",
                    lock_tx_hash=lock_tx_hash,
                )
                session.add(escrow_record)
            session.commit()
    except Exception as e:
        _logger.warning("Failed to persist escrow to DB after lock: %s", e)

    _logger.info(
        "Escrow created and locked: contract_id=%s job_id=%s amount=%s tx=%s", contract_id, job_id, amount, lock_tx_hash
    )
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "buyer": buyer,
        "provider": provider,
        "amount": str(amount_dec),
        "lock_tx_hash": lock_tx_hash,
        "message": message,
    }


@router.post("/escrow/{job_id}/release", summary="Release escrow to provider")
async def release_escrow(job_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """Release locked funds to the provider after job completion.
    Accepts optional job_tx_hash as proof of work reference."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")

    job_tx_hash = request.get("job_tx_hash")

    with session_scope() as session:
        record = session.get(Escrow, job_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"No escrow record found for job_id={job_id}")
        if record.status != "locked":
            raise HTTPException(
                status_code=409,
                detail=f"Escrow for job_id={job_id} is not locked (status={record.status})",
            )

    contract_id = _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")

    contract = mgr.escrow_contracts.get(contract_id)
    if contract:
        for ms in contract.milestones:
            ms["completed"] = True
            ms["verified"] = True
        from ..contracts.escrow import EscrowState

        contract.state = EscrowState.JOB_COMPLETED

    ok, message = await mgr.release_full_payment(contract_id)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    released_amount = contract.released_amount if contract else Decimal(0)
    released_at = datetime.now(UTC)

    # Submit the on-chain release *before* marking the DB row released, so a
    # submission failure leaves the escrow locked and retryable.
    provider_addr = record.provider
    tx_hash = await _submit_payment_tx(provider_addr, released_amount, job_id, contract_id)
    if not tx_hash:
        raise HTTPException(status_code=502, detail="ESCROW_RELEASE transaction submission failed; escrow remains locked")

    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record:
                record.status = "released"
                record.released_at = released_at
                record.job_tx_hash = job_tx_hash or tx_hash
                session.commit()
    except Exception as e:
        _logger.warning("Failed to update escrow release status in DB: %s", e)

    _logger.info("Escrow released: contract_id=%s job_id=%s tx=%s", contract_id, job_id, tx_hash)
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "message": message,
        "released_amount": str(released_amount),
        "tx_hash": tx_hash,
        "released_at": released_at.isoformat(),
    }


@router.post("/escrow/{job_id}/refund", summary="Refund escrow to buyer")
async def refund_escrow(job_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refund locked funds back to the buyer."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")
    contract_id = _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")
    reason = (body or {}).get("reason", "buyer_requested")
    success, message = await mgr.refund_contract(contract_id, reason)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    # Refund is not implemented as an on-chain transaction in this release;
    # record the intent and leave the locked funds in the node wallet.
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record:
                record.status = "refunded"
                record.refunded_at = datetime.now(UTC)
                session.commit()
    except Exception as e:
        _logger.warning("Failed to update escrow refund status in DB: %s", e)

    _logger.info("Escrow refunded: contract_id=%s job_id=%s", contract_id, job_id)
    return {"success": True, "contract_id": contract_id, "job_id": job_id, "message": message}


@router.get("/escrow/{job_id}", summary="Get escrow state")
async def get_escrow(job_id: str) -> dict[str, Any]:
    """Get current escrow state for a job."""
    mgr = get_escrow_manager()
    db_record: Escrow | None = None
    try:
        with session_scope() as session:
            db_record = session.get(Escrow, job_id)
    except Exception as e:
        _logger.warning("Failed to query Escrow DB: %s", e)
    if mgr is not None:
        contract_id = _find_contract_id(mgr, job_id)
        if contract_id:
            contract = mgr.escrow_contracts.get(contract_id)
            if contract:
                return {
                    "job_id": job_id,
                    "contract_id": contract_id,
                    "state": contract.state.value,
                    "buyer": contract.client_address,
                    "provider": contract.agent_address,
                    "amount": str(contract.amount),
                    "released_amount": str(contract.released_amount),
                    "refunded_amount": str(contract.refunded_amount),
                    "created_at": db_record.created_at.isoformat() if db_record else None,
                    "released_at": db_record.released_at.isoformat() if db_record and db_record.released_at else None,
                    "status": db_record.status if db_record else None,
                    "lock_tx_hash": db_record.lock_tx_hash if db_record else None,
                }
    if db_record:
        return {
            "job_id": job_id,
            "contract_id": None,
            "state": db_record.status,
            "buyer": db_record.buyer,
            "provider": db_record.provider,
            "amount": str(db_record.amount),
            "released_amount": str(db_record.amount) if db_record.status == "released" else "0",
            "refunded_amount": str(db_record.amount) if db_record.status == "refunded" else "0",
            "created_at": db_record.created_at.isoformat(),
            "released_at": db_record.released_at.isoformat() if db_record.released_at else None,
            "status": db_record.status,
            "lock_tx_hash": db_record.lock_tx_hash,
        }
    raise HTTPException(status_code=404, detail=f"No escrow found for job_id={job_id}") from None


def _find_contract_id(mgr: Any, job_id: str) -> str | None:
    """Find contract_id by job_id in EscrowManager."""
    for cid, contract in mgr.escrow_contracts.items():
        if contract.job_id == job_id:
            return str(cid)
    return None
