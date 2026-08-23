"""
Escrow RPC endpoints for the blockchain node.
Provides create/release/refund/get endpoints backed by EscrowManager and Escrow DB model.
"""

from __future__ import annotations
from aitbc.constants import BLOCKCHAIN_RPC_URL

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException

from aitbc.network import SharedHttpClient
from aitbc.crypto.crypto import derive_ethereum_address, sign_transaction_hash
from aitbc.crypto.signature_recovery import canonical_address
from eth_utils import keccak

from ..contracts.escrow import EscrowState, get_escrow_manager
from ..database import session_scope
from ..logger import get_logger
from ..models import Account, Escrow, Stake

_HUB_RPC_URL = os.getenv("HUB_RPC_URL", BLOCKCHAIN_RPC_URL)
_CHAIN_ID = os.getenv("CHAIN_ID", os.getenv("SUPPORTED_CHAINS", "ait-hub.aitbc.bubuit.net"))
_NODE_WALLET = os.getenv("NODE_WALLET_ADDRESS", os.getenv("GENESIS_WALLET_ADDRESS", ""))
_logger = get_logger(__name__)
router = APIRouter(tags=["escrow"])


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

# v0.7.3: ESCROW_RELEASE may be signed by a dedicated non-genesis key.
_ESCROW_RELEASE_PRIVATE_KEY = os.getenv("ESCROW_RELEASE_PRIVATE_KEY", "")
_ESCROW_RELEASE_ADDRESS = os.getenv("ESCROW_RELEASE_ADDRESS", "")


def _compute_tx_signing_hash(tx: dict[str, Any]) -> str:
    """Return the keccak hash the RPC verifies for a transaction signature."""
    has_amount = "amount" in tx
    tx_for_sign = {k: v for k, v in tx.items() if k not in ("signature", "sig") and not (has_amount and k == "value")}
    canonical = json.dumps(tx_for_sign, sort_keys=True, separators=(",", ":")).encode()
    return "0x" + keccak(canonical).hex()


def _to_canonical(address: str) -> str:
    """Return the ait1/canonical form of an address, falling back to input."""
    try:
        return canonical_address(address)
    except Exception:
        return str(address)


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
        _logger.warning("ESCROW_RELEASE: account creation check failed for %s: %s", address, e)
    return False


def _get_settlement_key() -> str:
    """Return the configured non-genesis escrow release key, falling back to genesis."""
    if _ESCROW_RELEASE_PRIVATE_KEY:
        return _ESCROW_RELEASE_PRIVATE_KEY
    if _GENESIS_WALLET_PRIVATE_KEY:
        _logger.warning(
            "ESCROW_RELEASE: ESCROW_RELEASE_PRIVATE_KEY is not set; signing payouts with the "
            "genesis key. Configure a dedicated settlement key to decouple settlement from genesis."
        )
    return _GENESIS_WALLET_PRIVATE_KEY


def _get_settlement_address() -> str | None:
    """Return the canonical settlement address for ESCROW_RELEASE signing.

    The address must be the one the signing key actually controls: the RPC
    verifies the signature against the transaction ``from`` field, so a
    key/address mismatch produces a 403 and the provider is never paid. When
    ``ESCROW_RELEASE_ADDRESS`` is set it is checked against the address derived
    from the signing key and a mismatch is refused rather than submitted.
    """
    key = _get_settlement_key()
    if not key:
        return None
    try:
        derived = canonical_address(derive_ethereum_address(key))
    except Exception as e:
        _logger.error("ESCROW_RELEASE: failed to derive settlement address: %s", e)
        return None
    if not _ESCROW_RELEASE_ADDRESS:
        return derived
    configured = canonical_address(_ESCROW_RELEASE_ADDRESS)
    if configured != derived:
        _logger.error(
            "ESCROW_RELEASE: settlement key/address mismatch - ESCROW_RELEASE_ADDRESS is %s but the "
            "configured signing key controls %s. Refusing to submit a transaction the RPC would "
            "reject; fix ESCROW_RELEASE_PRIVATE_KEY / ESCROW_RELEASE_ADDRESS in the node environment.",
            configured,
            derived,
        )
        return None
    return configured


async def _auto_stake(provider: str, amount: int, chain_id: str) -> str | None:
    """Stake a portion of released escrow for the provider without requiring a signature.

    This is a protocol-level reinvestment triggered from the escrow release path.
    The provider's on-chain account is expected to have just been credited by the
    ESCROW_RELEASE transaction.
    """
    if not provider or amount <= 0:
        return None
    try:
        with session_scope() as session:
            canonical = canonical_address(provider)
            address = canonical if canonical else provider.lower().strip()
            account = session.get(Account, (chain_id, address))
            if not account:
                _logger.warning("AUTO_STAKE: no account for %s, creating with zero balance", address)
                account = Account(chain_id=chain_id, address=address, balance=0, nonce=0)
                session.add(account)
            if account.balance < amount:
                _logger.warning("AUTO_STAKE: insufficient balance for %s: %s < %s", address, account.balance, amount)
                return None
            account.balance -= amount
            session.add(account)
            locked_until = datetime.now(UTC) + timedelta(days=30)
            stake = Stake(
                chain_id=chain_id,
                address=address,
                amount=amount,
                locked_until=locked_until,
                status="active",
            )
            session.add(stake)
            session.commit()
            session.refresh(stake)
            _logger.info("AUTO_STAKE: %s staked %s, stake_id=%s", address, amount, stake.id)
            # Stake.id is an int; every consumer (the release response, the
            # coordinator's ReceiptView.reinvest_stake_id) declares it a string.
            return str(stake.id)
    except Exception as e:
        _logger.error("AUTO_STAKE failed: %s", e)
    return None


# Safety bound on an already job_id-filtered result set; a job should match at most one
# release. This is no longer a history scan: the RPC filters by payload job_id in SQL.
_RELEASE_LOOKUP_LIMIT = int(os.getenv("ESCROW_RELEASE_LOOKUP_LIMIT", "10"))


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


async def _find_existing_release(job_id: str) -> str | None:
    """Return the hash of an ESCROW_RELEASE already on-chain for ``job_id``, if any.

    A retry must never pay twice. Once a first attempt is mined the nonce check rejects
    a replay, which looks like a failure even though the provider was paid -- so a
    reconciler that trusted the failure alone would retry forever. This lookup tells the
    two apart, and lets a retry return the transaction that already settled.

    The query filters on payload job_id server-side. An unfiltered scan was not merely
    slow: /transactions returns rows oldest-first and truncates to ``limit``, so a bounded
    scan silently missed recent settlements -- exactly the ones a retry asks about.
    """
    try:
        r = await SharedHttpClient.get(
            f"{_HUB_RPC_URL}/transactions?transaction_type=ESCROW_RELEASE&job_id={job_id}&limit={_RELEASE_LOOKUP_LIMIT}"
        )
        if r.status_code != 200:
            return None
        for tx in r.json() or []:
            # Re-check the payload: an older node without the job_id filter would
            # otherwise return unrelated releases and settle the wrong job.
            if (tx.get("payload") or {}).get("job_id") == job_id:
                settled_hash = tx.get("tx_hash")
                return str(settled_hash) if settled_hash else None
    except Exception as e:
        _logger.warning("ESCROW_RELEASE: settled-release lookup failed for job_id=%s: %s", job_id, e)
    return None


async def _submit_payment_tx(buyer: str, provider: str, amount: Decimal, job_id: str, contract_id: str) -> str | None:
    """Submit an ESCROW_RELEASE transaction to the blockchain so payment is on-chain."""
    amount_seconds = int(amount * 3600)
    amount_int = amount_seconds if amount_seconds > 0 else int(amount)
    if amount_int <= 0:
        return None
    try:
        # Never pay a job twice: if it already settled, hand back that transaction.
        existing_release = await _find_existing_release(job_id)
        if existing_release:
            _logger.info(
                "ESCROW_RELEASE already settled for job_id=%s (%s); not resubmitting",
                job_id,
                existing_release,
            )
            return existing_release

        settlement_key = _get_settlement_key()
        if not settlement_key:
            _logger.warning("ESCROW_RELEASE TX skipped: no settlement private key configured")
            return None

        settlement_address = _get_settlement_address()
        if not settlement_address:
            _logger.warning("ESCROW_RELEASE TX skipped: could not resolve settlement address")
            return None

        sender = settlement_address

        # The settlement account must exist before a TRANSFER-style transaction can be applied.
        if not await _create_account_if_missing(sender, _CHAIN_ID):
            _logger.warning("ESCROW_RELEASE TX skipped: could not create settlement account (sender=%s)", sender)
            return None

        # The provider account must exist before a TRANSFER-style transaction can be applied.
        if not await _create_account_if_missing(provider, _CHAIN_ID):
            _logger.warning("ESCROW_RELEASE TX skipped: could not create provider account (provider=%s)", provider)
            return None

        # Re-resolve after creation; use canonical ait1 form for the state layer.
        recipient = await _resolve_chain_account(provider) or _NODE_WALLET
        if not recipient:
            _logger.warning("ESCROW_RELEASE TX skipped: could not resolve recipient (provider=%s)", provider)
            return None

        nonce = await _get_account_nonce(sender)
        tx = {
            "from": sender,
            "to": recipient,
            "amount": amount_int,
            "fee": max(36, amount_int // 100),
            "nonce": nonce,
            "type": "ESCROW_RELEASE",
            "chain_id": _CHAIN_ID,
            "payload": {
                "action": "escrow_release",
                "job_id": job_id,
                "contract_id": contract_id,
                "buyer_escrow_addr": buyer,
                "provider_escrow_addr": provider,
            },
        }
        # The payload carries no wall-clock timestamp on purpose: an identical retry
        # must hash identically so the mempool deduplicates it (mempool.add returns the
        # existing hash for a duplicate). Two concurrent release attempts would otherwise
        # build two different transactions sharing one nonce, and admission validates the
        # nonce against the account -- which has not advanced while the first is pending --
        # so both would be admitted and the provider paid twice. Settlement time is
        # recoverable from the including block; the local escrow row keeps released_at.
        # Sign with the configured non-genesis settlement key (or genesis as fallback).
        signing_hash = _compute_tx_signing_hash(tx)
        tx["signature"] = sign_transaction_hash(signing_hash, settlement_key)

        resp = await SharedHttpClient.post(f"{_HUB_RPC_URL}/transactions/marketplace", json=tx, timeout=5.0)
        if resp.status_code in (200, 201):
            result = resp.json()
            raw_tx_hash = result.get("transaction_hash")
            actual_tx_hash: str | None = str(raw_tx_hash) if raw_tx_hash else None
            _logger.info(
                "ESCROW_RELEASE TX submitted: hash=%s amount=%s from=%s to=%s", actual_tx_hash, amount_int, sender, recipient
            )
            return actual_tx_hash
        else:
            _logger.error(
                "ESCROW_RELEASE TX rejected %s for job_id=%s (provider %s was NOT paid on-chain): %s",
                resp.status_code,
                job_id,
                provider,
                resp.text[:200],
            )
    except Exception as e:
        _logger.error(
            "ESCROW_RELEASE TX submission failed for job_id=%s (provider %s was NOT paid on-chain): %s",
            job_id,
            provider,
            e,
        )
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
            tx_to_submit, _ = _build_lock_tx(job_id, buyer, provider, amount_dec, nonce, fee)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        tx_to_submit["signature"] = lock_signature
    else:
        raise HTTPException(status_code=400, detail="escrow lock is required: provide lock_tx or lock_signature") from None

    # Verify the lock tx moves the expected amount to the node wallet.
    try:
        expected_tx, _ = _build_lock_tx(job_id, buyer, provider, amount_dec, tx_to_submit.get("nonce", 0))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    if tx_to_submit.get("from") != expected_tx["from"]:
        raise HTTPException(status_code=400, detail="lock_tx from must be the buyer") from None
    if _to_canonical(tx_to_submit.get("to", "")) != _to_canonical(expected_tx["to"]):
        raise HTTPException(status_code=400, detail="lock_tx to must be the node wallet") from None
    if int(tx_to_submit.get("amount", 0)) != _ait_to_seconds(amount_dec):
        raise HTTPException(status_code=400, detail=f"lock_tx amount must be {_ait_to_seconds(amount_dec)}") from None
    payload = tx_to_submit.get("payload") or {}
    if payload.get("job_id") != job_id:
        raise HTTPException(status_code=400, detail="lock_tx payload job_id mismatch") from None
    if _to_canonical(payload.get("provider", "")) != _to_canonical(provider):
        raise HTTPException(status_code=400, detail="lock_tx payload provider mismatch") from None

    # Ensure the buyer has an on-chain account before the lock tx is admitted.
    if not await _create_account_if_missing(_to_canonical(buyer), _CHAIN_ID):
        raise HTTPException(status_code=400, detail=f"could not ensure buyer account exists: {buyer}") from None

    success, message, contract_id = await mgr.create_contract(
        job_id=job_id, client_address=buyer, agent_address=provider, amount=amount_dec
    )
    if not success:
        raise HTTPException(status_code=400, detail=message) from None

    lock_tx_hash = await _submit_lock_tx(tx_to_submit)

    # Fund the in-memory contract now that the lock has been submitted.
    if contract_id is None:
        raise HTTPException(status_code=500, detail="escrow contract_id missing after create")
    await mgr.fund_contract(contract_id, lock_tx_hash)

    try:
        with session_scope() as session:
            existing = session.get(Escrow, (job_id, _CHAIN_ID))
            if existing:
                existing.status = "locked"
                existing.lock_tx_hash = lock_tx_hash
                existing.buyer = _to_canonical(buyer)
                existing.provider = _to_canonical(provider)
                existing.amount = int(amount_dec)
            else:
                escrow_record = Escrow(
                    job_id=job_id,
                    chain_id=_CHAIN_ID,
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

    # Settlement must be possible before any escrow state is mutated. A node whose
    # settlement key and address disagree cannot pay the provider, and releasing
    # first would leave the escrow marked paid with nothing on-chain.
    if not _get_settlement_key() or not _get_settlement_address():
        _logger.error(
            "ESCROW_RELEASE: refusing to release job_id=%s - settlement key/address is missing or mismatched",
            job_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Settlement key/address is not configured correctly; escrow was not released",
        )

    job_tx_hash = request.get("job_tx_hash")

    # Reconciliation/duplicate release handling: if the row is already released,
    # return the stored result without resubmitting.
    try:
        with session_scope() as session:
            record = session.get(Escrow, (job_id, _CHAIN_ID))
            if record and record.released_at is not None:
                return {
                    "success": True,
                    "contract_id": getattr(record, "contract_id", None) or "",
                    "job_id": job_id,
                    "message": "Escrow already released",
                    "released_amount": str(record.amount),
                    "tx_hash": record.job_tx_hash or "",
                    "released_at": record.released_at.isoformat(),
                }
            if record is not None and record.status not in (None, "locked"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Escrow for job_id={job_id} is not locked (status={record.status})",
                )
    except HTTPException:
        raise
    except Exception as e:
        _logger.warning("Failed to check escrow release state: %s", e)

    contract_id = await _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")
    contract = mgr.escrow_contracts.get(contract_id)
    if contract:
        for ms in contract.milestones:
            ms["completed"] = True
            ms["verified"] = True
        from ..contracts.escrow import EscrowState

        contract.state = EscrowState.JOB_COMPLETED
    # Hold the per-contract lock across release and settlement so the rollback
    # snapshot cannot interleave with a concurrent release of this contract.
    async with mgr.release_lock(contract_id):
        release_snapshot = mgr.snapshot_release_state(contract_id)
        ok, message = await mgr.release_full_payment(contract_id)
        if not ok:
            raise HTTPException(status_code=400, detail=message)
        released_amount = contract.released_amount if contract else Decimal(0)
        buyer_addr = contract.client_address if contract else ""
        provider_addr = contract.agent_address if contract else ""
        # Allow caller to override the provider address for reinvestment (e.g. from payment meta_data).
        reinvest_address = request.get("auto_reinvest_address") or provider_addr or request.get("provider_address")
        auto_reinvest_pct = request.get("auto_reinvest_pct")

        # Settle on-chain first; only a confirmed transaction counts as a release.
        tx_hash = await _submit_payment_tx(buyer_addr, provider_addr, released_amount, job_id, contract_id)
        if not tx_hash:
            mgr.restore_after_failed_settlement(contract_id, release_snapshot)
            _logger.error(
                "Escrow release NOT settled on-chain: contract_id=%s job_id=%s provider=%s amount=%s. "
                "The release was rolled back so it can be retried.",
                contract_id,
                job_id,
                provider_addr,
                released_amount,
            )
            return {
                "success": False,
                "contract_id": contract_id,
                "job_id": job_id,
                "message": "Escrow release could not be settled on-chain; the provider was not paid",
                "released_amount": str(released_amount),
                "tx_hash": None,
                "settlement_status": "unsettled",
                "released_at": None,
                "reinvest_amount": "0",
                "reinvest_stake_id": None,
            }

        released_at = datetime.now(UTC)
        try:
            with session_scope() as session:
                record = session.get(Escrow, job_id)
                if record:
                    # A reconciliation retry re-releases an escrow that already settled,
                    # and _submit_payment_tx hands back the transaction that settled it.
                    # Keep the original timestamp: it is when the provider was actually
                    # paid. Overwriting it would date the payment to the retry instead.
                    if record.released_at is not None:
                        released_at = record.released_at
                    else:
                        record.released_at = released_at
                    if job_tx_hash:
                        record.job_tx_hash = job_tx_hash
                    session.commit()
        except Exception as e:
            _logger.warning("Failed to update released_at/job_tx_hash in DB: %s", e)
        reinvest_stake_id = None
        reinvest_amount = Decimal(0)
        if auto_reinvest_pct and reinvest_address and released_amount > 0:
            try:
                pct = Decimal(str(auto_reinvest_pct))
                if 0 < pct <= 100:
                    reinvest_amount_ait = (released_amount * pct / 100).quantize(Decimal("0.00000001"))
                    if reinvest_amount_ait > 0:
                        reinvest_amount_seconds = int(reinvest_amount_ait * 3600)
                        if reinvest_amount_seconds > 0:
                            reinvest_stake_id = await _auto_stake(reinvest_address, reinvest_amount_seconds, _CHAIN_ID)
                            reinvest_amount = reinvest_amount_ait
                        _logger.info(
                            "Escrow reinvestment: job_id=%s stake_id=%s amount=%s pct=%s",
                            job_id,
                            reinvest_stake_id,
                            reinvest_amount,
                            pct,
                        )
            except Exception as e:
                _logger.warning("Failed to auto-reinvest for job %s: %s", job_id, e)
        _logger.info("Escrow released: contract_id=%s job_id=%s tx=%s", contract_id, job_id, tx_hash)
        return {
            "success": True,
            "contract_id": contract_id,
            "job_id": job_id,
            "message": message,
            "released_amount": str(released_amount),
            "tx_hash": tx_hash,
            "settlement_status": "settled" if tx_hash else "unsettled",
            "released_at": released_at.isoformat(),
            "reinvest_amount": str(reinvest_amount),
            "reinvest_stake_id": reinvest_stake_id,
        }


@router.post("/escrow/{job_id}/refund", summary="Refund escrow to buyer")
async def refund_escrow(job_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refund locked funds back to the buyer."""
    mgr = get_escrow_manager()
    if mgr is None:
        raise HTTPException(status_code=503, detail="EscrowManager not initialised")
    # Reconciliation/duplicate refund handling: if the row is already refunded,
    # return the stored result without resubmitting.
    try:
        with session_scope() as session:
            record = session.get(Escrow, (job_id, _CHAIN_ID))
            if record and record.refunded_at is not None:
                return {
                    "success": True,
                    "contract_id": "",
                    "job_id": job_id,
                    "message": "Escrow already refunded",
                    "refund_tx_hash": record.refund_tx_hash or "",
                }
    except Exception as e:
        _logger.warning("Failed to check escrow refund state: %s", e)

    contract_id = await _find_contract_id(mgr, job_id)
    if contract_id is None:
        raise HTTPException(status_code=404, detail=f"No escrow contract found for job_id={job_id}")
    contract = mgr.escrow_contracts.get(contract_id)
    if contract and contract.state in {EscrowState.RELEASED, EscrowState.REFUNDED, EscrowState.EXPIRED}:
        if contract.state == EscrowState.REFUNDED:
            try:
                with session_scope() as session:
                    record = session.get(Escrow, job_id)
                    return {
                        "success": True,
                        "contract_id": contract_id,
                        "job_id": job_id,
                        "message": "Escrow already refunded",
                        "refund_tx_hash": record.refund_tx_hash if record else None,
                    }
            except Exception as e:
                _logger.warning("Failed to read refund_tx_hash for already-refunded job %s: %s", job_id, e)
        raise HTTPException(status_code=400, detail=f"Escrow already in final state: {contract.state.value}")
    reason = (body or {}).get("reason", "buyer_requested")
    success, message = await mgr.refund_contract(contract_id, reason)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    refunded_at = datetime.now(UTC)
    refund_tx_hash = f"0x{hashlib.sha256(f'{job_id}:{refunded_at.isoformat()}'.encode()).hexdigest()}"
    try:
        with session_scope() as session:
            record = session.get(Escrow, job_id)
            if record:
                record.status = "refunded"
                record.refunded_at = refunded_at
                record.refund_tx_hash = refund_tx_hash
                session.commit()
    except Exception as e:
        _logger.warning("Failed to update refunded_at for job %s: %s", job_id, e)
    _logger.info("Escrow refunded: contract_id=%s job_id=%s tx=%s", contract_id, job_id, refund_tx_hash)
    return {
        "success": True,
        "contract_id": contract_id,
        "job_id": job_id,
        "message": message,
        "refund_tx_hash": refund_tx_hash,
    }


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
        contract_id = await _find_contract_id(mgr, job_id)
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
                    "refunded_at": db_record.refunded_at.isoformat() if db_record and db_record.refunded_at else None,
                    "refund_tx_hash": db_record.refund_tx_hash if db_record else None,
                    "status": db_record.status if db_record else None,
                    "lock_tx_hash": db_record.lock_tx_hash if db_record else None,
                }
    if db_record:
        return {
            "job_id": job_id,
            "contract_id": None,
            "state": db_record.status
            or ("refunded" if db_record.refunded_at else ("released" if db_record.released_at else "funded")),
            "buyer": db_record.buyer,
            "provider": db_record.provider,
            "amount": str(db_record.amount),
            "released_amount": str(db_record.amount) if db_record.released_at else "0",
            "refunded_amount": str(db_record.amount) if db_record.refunded_at else "0",
            "created_at": db_record.created_at.isoformat(),
            "released_at": db_record.released_at.isoformat() if db_record.released_at else None,
            "refunded_at": db_record.refunded_at.isoformat() if db_record.refunded_at else None,
            "refund_tx_hash": db_record.refund_tx_hash,
            "status": db_record.status,
            "lock_tx_hash": db_record.lock_tx_hash,
        }
    raise HTTPException(status_code=404, detail=f"No escrow found for job_id={job_id}") from None


async def _find_contract_id(mgr: Any, job_id: str) -> str | None:
    """Find contract_id by job_id, loading from DB if missing."""
    for cid, contract in mgr.escrow_contracts.items():
        if contract.job_id == job_id:
            return str(cid)
    # Load from DB on demand before giving up.
    try:
        contract = await mgr.get_or_load_contract(job_id)
        if contract:
            return str(contract.contract_id)
    except Exception as e:
        _logger.warning("Failed to load contract for job %s: %s", job_id, e)
    return None
